"""Embeddings-based candidate generation (Phase 11 / B1).

Computes Gemini text embeddings for each page, then uses cosine similarity
to shortlist plausible source -> target link pairs BEFORE the recommendation
AI calls. The downstream AI still scores + anchors each pair, but it stops
exploring an open universe of pages and instead works from a vetted shortlist.

Why this matters:
- Open-ended exploration (the legacy path) sends the AI big batches of pages
  and asks "find linking opportunities". Most of what comes back gets dropped
  by `score_pair` hard filters anyway, so we paid AI tokens to surface invalid
  pairs. Embedding similarity is ~1000x cheaper per pair than an AI call.
- Embeddings + hard filters cut the shortlist by ~90% before the AI sees it,
  which is the foundation Phase B9 (cap removal) builds on.

Cache: embeddings are deterministic for fixed (model, page text). We hash the
sorted page-text set + model name and persist embeddings under
/tmp/ila_embeddings/<hash>.pkl. Re-runs on the same crawl skip embedding
generation entirely. Cache is best-effort -- if pickle fails, we recompute.

Multilingual: defaults to gemini-embedding-001, which is natively multilingual
and the right pick for BC's 14+ language portfolio. Override via
GEMINI_EMBEDDING_MODEL env var if a deployment doesn't have access yet.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import time
from pathlib import Path

import numpy as np
from google import genai
from google.genai import errors as genai_errors


# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #

EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

# 768 strikes a good cost/quality balance: 4x smaller than the 3072 default,
# negligible quality drop on slug-level semantic similarity, faster cosine
# computation and 4x less RAM/disk on the cache.
EMBEDDING_DIM = int(os.environ.get("ILA_EMBEDDING_DIM", "768"))

# Gemini's batch endpoint accepts up to 100 inputs per call.
EMBEDDING_BATCH_SIZE = 100

# How many target candidates to keep per source URL. 30 is empirically
# enough to cover the relevant cocoon + adjacent topical neighbors.
TOP_N_CANDIDATES_PER_SOURCE = int(os.environ.get("ILA_TOP_N_CANDIDATES", "30"))

# Floor on cosine similarity. Below this, the pair is too topically distant
# to be worth scoring even if it's in a source's top-N.
SIMILARITY_FLOOR = float(os.environ.get("ILA_SIM_FLOOR", "0.55"))

# Hard cap on total candidates after similarity filtering, before hard
# filters run. Belt-and-suspenders against runaway cost on huge sites.
MAX_CANDIDATES = int(os.environ.get("ILA_MAX_CANDIDATES", "20000"))

CACHE_DIR = Path(os.environ.get("ILA_EMBEDDING_CACHE_DIR", "/tmp/ila_embeddings"))


# --------------------------------------------------------------------------- #
# Page text builder
# --------------------------------------------------------------------------- #

def page_text_for_embedding(ctx: dict) -> str:
    """Build the embedding text for a page from its context.

    We embed slug + target keyword + content type + a sample of inbound
    anchors. The full URL is too domain-noisy; the slug carries the topical
    signal. Anchors capture how *other pages* describe this one -- a strong
    semantic signal that the AI also uses.
    """
    parts: list[str] = []
    slug = ctx.get("slug", "")
    if slug:
        # Replace path delimiters with spaces so tokenizer sees them as words.
        parts.append(slug.replace("/", " ").replace("-", " ").replace("_", " ").strip())
    if ctx.get("target_keyword"):
        parts.append(str(ctx["target_keyword"]))
    if ctx.get("content_type"):
        parts.append(f"type: {ctx['content_type']}")
    anchors = ctx.get("inbound_anchors") or []
    if anchors:
        parts.append("anchors: " + ", ".join(str(a) for a in anchors[:5] if a))
    text = " | ".join(p for p in parts if p)
    # Embedding APIs reject empty strings; fall back to the URL as a last resort.
    return text or ctx.get("url", "<empty>")


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

def _cache_key(model: str, dim: int, page_texts: dict[str, str]) -> str:
    """Stable hash over (model, dim, {url -> text}). 16 hex chars is plenty."""
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\0")
    h.update(str(dim).encode("utf-8"))
    h.update(b"\0")
    for url in sorted(page_texts):
        h.update(url.encode("utf-8"))
        h.update(b"\0")
        h.update(page_texts[url].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _load_cache(key: str) -> dict[str, np.ndarray] | None:
    path = CACHE_DIR / f"{key}.pkl"
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _save_cache(key: str, embeddings: dict[str, np.ndarray]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"{key}.pkl"
        tmp = path.with_suffix(".pkl.tmp")
        with tmp.open("wb") as f:
            pickle.dump(embeddings, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
    except Exception:
        # Cache is best-effort. Failure here just means next run recomputes.
        pass


# --------------------------------------------------------------------------- #
# Embedding generation
# --------------------------------------------------------------------------- #

def compute_page_embeddings(
    contexts: list[dict],
    client: genai.Client,
    progress_callback=None,
    model: str | None = None,
    dim: int | None = None,
) -> tuple[dict[str, np.ndarray], dict]:
    """Compute (or load from cache) embeddings for all pages in `contexts`.

    Returns ({url: vector}, stats_dict). stats_dict has keys:
        cache_hit (bool), pages (int), batches_called (int), error (str|None).
    """
    model = model or EMBEDDING_MODEL
    dim = dim or EMBEDDING_DIM
    stats = {"cache_hit": False, "pages": 0, "batches_called": 0, "error": None}

    if not contexts:
        return {}, stats

    page_texts = {ctx["url"]: page_text_for_embedding(ctx) for ctx in contexts}
    stats["pages"] = len(page_texts)

    cache_key = _cache_key(model, dim, page_texts)
    cached = _load_cache(cache_key)
    if cached and all(url in cached for url in page_texts):
        stats["cache_hit"] = True
        return {url: cached[url] for url in page_texts}, stats

    embeddings: dict[str, np.ndarray] = {}
    urls = list(page_texts.keys())
    total_batches = (len(urls) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    for batch_idx, start in enumerate(range(0, len(urls), EMBEDDING_BATCH_SIZE), start=1):
        batch_urls = urls[start:start + EMBEDDING_BATCH_SIZE]
        batch_texts = [page_texts[u] for u in batch_urls]

        if progress_callback:
            progress_callback(batch=batch_idx, total_batches=total_batches)

        for attempt in range(3):
            try:
                response = client.models.embed_content(
                    model=model,
                    contents=batch_texts,
                    config={
                        "task_type": "SEMANTIC_SIMILARITY",
                        "output_dimensionality": dim,
                    },
                )
                stats["batches_called"] += 1
                for url, emb in zip(batch_urls, response.embeddings):
                    vec = np.asarray(emb.values, dtype=np.float32)
                    # gemini-embedding-001 with output_dimensionality < default
                    # returns un-normalized vectors -- caller normalizes before
                    # cosine. We store as-is so callers can re-normalize cheaply.
                    embeddings[url] = vec
                break
            except genai_errors.ClientError as e:
                msg = str(e)
                if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < 2:
                    time.sleep(30 * (attempt + 1))
                    continue
                stats["error"] = msg[:200]
                return embeddings, stats
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                stats["error"] = str(e)[:200]
                return embeddings, stats

    _save_cache(cache_key, embeddings)
    return embeddings, stats


# --------------------------------------------------------------------------- #
# Similarity + candidate generation
# --------------------------------------------------------------------------- #

def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def cosine_similarity_matrix(
    embeddings: dict[str, np.ndarray],
) -> tuple[list[str], np.ndarray]:
    """Build a cosine-similarity matrix from a dict of embeddings.

    Returns (urls, matrix) with matrix[i][j] = cosine_sim(emb[urls[i]], emb[urls[j]]).
    Diagonal is 1.0 (untouched here -- caller may overwrite).
    """
    urls = list(embeddings.keys())
    if not urls:
        return [], np.zeros((0, 0), dtype=np.float32)
    stacked = np.stack([embeddings[u] for u in urls])
    normed = _normalize_matrix(stacked)
    return urls, normed @ normed.T


def generate_candidates(
    embeddings: dict[str, np.ndarray],
    top_n: int = TOP_N_CANDIDATES_PER_SOURCE,
    floor: float = SIMILARITY_FLOOR,
    max_candidates: int = MAX_CANDIDATES,
) -> list[tuple[str, str, float]]:
    """Generate (source_url, target_url, similarity) candidate pairs.

    For each source URL, returns its top-N most similar URLs above `floor`,
    excluding self-pairs. Pairs are NOT deduplicated by undirected edge --
    (A, B) and (B, A) are both valid because directional asymmetry matters
    in internal linking (a high-PR page linking to an orphan != the reverse).

    `max_candidates` is a hard ceiling -- if the raw shortlist exceeds it,
    we keep the top by similarity globally.
    """
    urls, sim = cosine_similarity_matrix(embeddings)
    if not urls:
        return []

    # Exclude self-pairs from the top-N selection.
    np.fill_diagonal(sim, -1.0)

    candidates: list[tuple[str, str, float]] = []
    for i, src in enumerate(urls):
        row = sim[i]
        # argpartition is O(n) for top-k vs O(n log n) for argsort.
        if top_n < len(row):
            top_idx = np.argpartition(row, -top_n)[-top_n:]
        else:
            top_idx = np.arange(len(row))
        for j in top_idx:
            score = float(row[j])
            if score < floor:
                continue
            candidates.append((src, urls[j], score))

    if len(candidates) > max_candidates:
        # Keep the globally most-similar pairs.
        candidates.sort(key=lambda t: t[2], reverse=True)
        candidates = candidates[:max_candidates]

    return candidates
