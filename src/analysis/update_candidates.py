"""Anchor-update detection — surfaces existing crawl links with weak anchors.

A natural extension of `removal_candidates.py`. Same engine pattern, same UX
shape: surface for review, never auto-execute. Targets existing links whose
anchor text is generic ("click here", "read more"), empty, single-letter, or
just the domain name. Suggests a stronger anchor derived from the target's
priority keyword (when available) or the target slug.

Skipped when the (source, target) pair already shows up as a removal
candidate — no point improving the anchor on a link you'd remove.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd


# Anchors that are SEO-weak: generic, non-descriptive, or pure-bracket text.
# Case-insensitive match against the trimmed anchor.
_WEAK_ANCHORS: set[str] = {
    "", "click here", "click", "here", "read more", "more", "see", "see more",
    "this", "this page", "this article", "link", "this link", "go", "go here",
    "view", "view more", "view here", "learn more", "details", "info",
    "site", "website", "the site", "the website", "page", "the page",
    ">", ">>", "→", "...",
}


def _is_domain_only_anchor(anchor: str, target_url: str) -> bool:
    """True when the anchor is basically just the target's domain name."""
    if not anchor or not target_url:
        return False
    try:
        host = urlparse(target_url).hostname or ""
    except Exception:
        return False
    host = host.lower().lstrip("www.")
    a = anchor.strip().lower().lstrip("www.").rstrip("/")
    return bool(host) and a == host


def _suggest_anchor(
    target_url: str,
    target_ctx: dict | None,
) -> str | None:
    """Best replacement anchor for a weak existing one.

    Prefers the target's priority keyword, then the cleaned URL slug.
    Returns None when neither is available (caller falls back to keeping the
    existing anchor — we don't suggest something equally weak).
    """
    if target_ctx and target_ctx.get("target_keyword"):
        return str(target_ctx["target_keyword"]).strip() or None
    try:
        path = urlparse(target_url).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        if slug:
            return slug.replace("-", " ").replace("_", " ").strip() or None
    except Exception:
        pass
    return None


def _is_weak_anchor(anchor: str, target_url: str) -> tuple[bool, str]:
    """Classify the anchor. Returns (is_weak, reason)."""
    a = (anchor or "").strip()
    if not a:
        return True, "empty anchor"
    if len(a) <= 2:
        return True, "anchor is too short (≤2 chars)"
    low = a.lower()
    if low in _WEAK_ANCHORS:
        return True, f'generic anchor ("{a}")'
    if _is_domain_only_anchor(a, target_url):
        return True, f'domain-only anchor ("{a}")'
    return False, ""


def compute_update_candidates(
    cleaned_df: pd.DataFrame,
    contexts_by_url: dict[str, dict],
    removal_pairs: set[tuple[str, str]] | None = None,
) -> tuple[list[dict], dict]:
    """Identify existing crawl links worth re-anchoring.

    Dedups on (Source, Destination) — Screaming Frog emits one row per
    `<a>` element, so a page with adjacent split anchors (e.g.
    `<a>Bet</a><a>s</a><a>son</a>` all linking to the same URL) produces
    multiple SF rows for what's functionally one link signal. If ANY parallel
    anchor on that pair is non-weak, the page already has a strong signal
    to that target and we skip the pair entirely — fixing the fragmentation
    is HTML cleanup, not an anchor-update task.

    Returns (candidates, stats). Each candidate dict has shape:
        `source_url`, `target_url`, `existing_anchor`, `suggested_anchor`,
        `reason`, `update_type="weak_anchor"`.
    """
    if cleaned_df is None or len(cleaned_df) == 0:
        return [], {
            "total": 0, "scored_links": 0,
            "skipped_no_suggestion": 0, "skipped_strong_sibling": 0,
        }

    removal_pairs = removal_pairs or set()

    # Group all parallel edges by (Source, Destination). For each pair we
    # need every anchor variant so we can decide if at least one is strong.
    anchors_by_pair: dict[tuple[str, str], list[str]] = {}
    for src, tgt, anc in zip(
        cleaned_df["Source"], cleaned_df["Destination"], cleaned_df["Anchor"]
    ):
        if not src or not tgt or src == tgt:
            continue
        anchors_by_pair.setdefault((src, tgt), []).append(anc or "")

    candidates: list[dict] = []
    skipped_no_suggestion = 0
    skipped_strong_sibling = 0
    scored = 0

    for (src, tgt), anchors in anchors_by_pair.items():
        if (src, tgt) in removal_pairs:
            # Removal supersedes update — no point fixing the anchor on
            # a link the team is about to delete.
            continue

        scored += 1

        # Classify each parallel anchor. If any one of them is strong, the
        # page already signals this target well — skip the whole pair.
        weak_anchors: list[tuple[str, str]] = []  # (anchor, reason)
        has_strong = False
        for anc in anchors:
            is_weak, reason = _is_weak_anchor(anc, tgt)
            if is_weak:
                weak_anchors.append((anc, reason))
            else:
                has_strong = True
                break

        if has_strong:
            skipped_strong_sibling += 1
            continue
        if not weak_anchors:
            continue

        tgt_ctx = contexts_by_url.get(tgt)
        suggestion = _suggest_anchor(tgt, tgt_ctx)
        if not suggestion:
            skipped_no_suggestion += 1
            continue

        # Pick the longest weak anchor as the representative — gives the team
        # the most descriptive existing example to compare against.
        representative = max(weak_anchors, key=lambda x: len(x[0]))
        if suggestion.strip().lower() == representative[0].strip().lower():
            continue

        # Reason mentions multiplicity when relevant so the team knows to
        # check for fragmented HTML on the source page.
        if len(weak_anchors) > 1:
            fragments = ", ".join(f'"{a}"' for a, _ in weak_anchors[:5])
            reason_text = (
                f"Weak anchor: {len(weak_anchors)} parallel anchors all weak "
                f"({fragments}). Suggested: \"{suggestion}\""
            )
        else:
            anc, why = weak_anchors[0]
            reason_text = f"Weak anchor: {why}. Suggested: \"{suggestion}\""

        candidates.append({
            "source_url": src,
            "target_url": tgt,
            "existing_anchor": representative[0],
            "suggested_anchor": suggestion,
            "reason": reason_text,
            "update_type": "weak_anchor",
        })

    stats = {
        "total": len(candidates),
        "scored_links": scored,
        "skipped_no_suggestion": skipped_no_suggestion,
        "skipped_strong_sibling": skipped_strong_sibling,
    }
    return candidates, stats
