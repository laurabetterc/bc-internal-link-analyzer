"""Coverage guarantee — every page must receive AND send at least one link.

Operates on the FULL cleaned crawl (every URL appearing in cleaned_df), not
just the 168/500 contexts the AI sees. After AI recommendations + orphan
guarantee + link budget have run, this pass:

  1. Computes final inbound = (crawl inbound count) + (recommended inbound count)
  2. Computes final outbound = (crawl outbound count) + (recommended outbound count)
  3. For every URL with final_inbound == 0  -> add a [Coverage fallback] inbound rec
  4. For every URL with final_outbound == 0 -> add a [Coverage fallback] outbound rec

Fallback selection mirrors `orphan_guarantee` but is symmetric:

  Inbound fallback (find a SOURCE to link FROM):
    1. Same-cocoon review page
    2. Same-cocoon code page
    3. Closest URL within same section/market by slug-token Jaccard
    4. Site-wide review hub (any review page)
    5. Homepage

  Outbound fallback (find a TARGET to link TO):
    1. Same-cocoon code page (funnel intent)
    2. Same-cocoon review page
    3. Closest URL within same section/market by slug-token Jaccard
    4. Site-wide review hub
    5. Homepage

Every fallback rec carries `is_coverage_fallback=True` and a Reason starting
with "[Coverage fallback]" so the SEO Content Manager can filter / triage them
separately from real AI judgments.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from src.analysis.market_detector import market_for_url
from src.cleaning.language import extract_lang_segment


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_TOKEN_SPLIT = re.compile(r"[\W_]+", re.UNICODE)


def _path_tokens(url: str) -> set[str]:
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return set()
    return {t for t in _TOKEN_SPLIT.split(path) if t and len(t) > 1 and not t.isdigit()}


def _root_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return None


def _detect_homepage(all_urls: set[str]) -> str | None:
    """Pick the most likely homepage from a URL set.

    Preference: bare-root URL (https://x.com/) if present, else the URL
    with the shortest path.
    """
    candidates = [u for u in all_urls if isinstance(u, str)]
    if not candidates:
        return None
    # Bare root
    for url in candidates:
        try:
            p = urlparse(url)
            if p.scheme and p.netloc and p.path in ("", "/"):
                return url
        except Exception:
            continue
    # Fallback: shortest path
    return min(candidates, key=lambda u: len(urlparse(u).path) if isinstance(u, str) else 999)


def _anchor_from_url(url: str, target_keyword: str | None = None) -> str:
    """Best-effort anchor text from URL slug. Used for coverage fallbacks
    where we don't have a deeper signal — beats 'click here'.
    """
    if target_keyword:
        return target_keyword
    try:
        path = urlparse(url).path.strip("/")
        if not path:
            return "homepage"
        last = path.rsplit("/", 1)[-1]
        # Convert slug to readable phrase
        text = re.sub(r"[\-_]+", " ", last).strip()
        return text or "read more"
    except Exception:
        return "read more"


def _section_or_market_key(url: str) -> tuple[str | None, str | None]:
    return extract_lang_segment(url), market_for_url(url)


# --------------------------------------------------------------------------- #
# Closest-URL fallback (slug Jaccard, within same section/market)
# --------------------------------------------------------------------------- #

def _closest_url(
    target: str,
    candidate_urls: list[str],
    used: set[str],
    require_same_section: bool = True,
) -> str | None:
    """Pick the URL whose slug shares the most tokens with `target`.

    Filters to candidates in the same section + same market when both signals
    are present. Excludes the target itself, anything in `used`, and self-loops.
    """
    if not candidate_urls:
        return None
    target_tokens = _path_tokens(target)
    if not target_tokens:
        return None
    t_section, t_market = _section_or_market_key(target)

    best_score = 0
    best_url: str | None = None
    for url in candidate_urls:
        if url == target or url in used:
            continue
        if require_same_section:
            u_section, u_market = _section_or_market_key(url)
            if t_section and u_section and t_section != u_section:
                continue
            if t_market and u_market and t_market != u_market:
                continue
        u_tokens = _path_tokens(url)
        if not u_tokens:
            continue
        overlap = len(target_tokens & u_tokens)
        if overlap > best_score:
            best_score = overlap
            best_url = url

    if best_score < 2:
        # Two shared tokens is the floor — below this, the "match" is just
        # site-prefix coincidence (e.g. /mx/apuestas/ tokens). Better to fall
        # through to homepage than recommend something topically random.
        return None
    return best_url


# --------------------------------------------------------------------------- #
# Fallback chains
# --------------------------------------------------------------------------- #

def _pick_inbound_fallback(
    target: str,
    cocoon_by_url: dict[str, list[str]],
    code_page_by_op: dict[str, str | None],
    review_page_by_op: dict[str, str | None],
    site_reviews: list[str],
    all_urls_list: list[str],
    homepage: str | None,
) -> tuple[str | None, str]:
    """Find a SOURCE to link FROM into `target`. Returns (url, reason)."""
    target_ops = cocoon_by_url.get(target, [])

    # 1 + 2: same-cocoon review, then same-cocoon code
    for op in target_ops:
        rev = review_page_by_op.get(op)
        if rev and rev != target:
            return rev, "same-cocoon review (coverage)"
    for op in target_ops:
        code = code_page_by_op.get(op)
        if code and code != target:
            return code, "same-cocoon code page (coverage)"

    # 3: closest URL within section/market
    closest = _closest_url(target, all_urls_list, used={target}, require_same_section=True)
    if closest:
        return closest, "slug-similarity in same section (coverage)"

    # 4: any review across all cocoons
    for rev in site_reviews:
        if rev != target:
            return rev, "site-wide review hub (coverage)"

    # 5: homepage
    if homepage and homepage != target:
        return homepage, "homepage (last-resort coverage)"

    return None, "no fallback source available"


def _pick_outbound_fallback(
    source: str,
    cocoon_by_url: dict[str, list[str]],
    code_page_by_op: dict[str, str | None],
    review_page_by_op: dict[str, str | None],
    site_reviews: list[str],
    all_urls_list: list[str],
    homepage: str | None,
) -> tuple[str | None, str]:
    """Find a TARGET for `source` to link TO. Returns (url, reason).

    Funnel preference: cocoon code page first (Rule 3 — code page is the
    PageRank destination), then review, then slug-similar, then site-wide
    review hub, then homepage.
    """
    source_ops = cocoon_by_url.get(source, [])

    # 1: same-cocoon code page (funnel)
    for op in source_ops:
        code = code_page_by_op.get(op)
        if code and code != source:
            return code, "same-cocoon code page (coverage funnel)"

    # 2: same-cocoon review
    for op in source_ops:
        rev = review_page_by_op.get(op)
        if rev and rev != source:
            return rev, "same-cocoon review (coverage)"

    # 3: closest URL within section/market
    closest = _closest_url(source, all_urls_list, used={source}, require_same_section=True)
    if closest:
        return closest, "slug-similarity in same section (coverage)"

    # 4: any review across all cocoons
    for rev in site_reviews:
        if rev != source:
            return rev, "site-wide review hub (coverage)"

    # 5: homepage
    if homepage and homepage != source:
        return homepage, "homepage (last-resort coverage)"

    return None, "no fallback target available"


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

def ensure_full_coverage(
    recommendations: list[dict],
    cleaned_df,
    cocoons: list[dict],
    page_type_lookup: dict[str, str],
) -> tuple[list[dict], dict]:
    """Add fallback recs so every URL in cleaned_df has both inbound and outbound.

    Args:
        recommendations: AI + post-pass recs accumulated so far
        cleaned_df: full cleaned link DataFrame (all URLs after Step 1+2 cleaning)
        cocoons: AI + deterministic cocoons (post-merge)
        page_type_lookup: {url: page_type} for type-aware fallbacks

    Returns:
        (recommendations_with_fallbacks, stats_dict)
    """
    stats: dict = {
        "total_urls": 0,
        "inbound_gaps_before": 0,
        "outbound_gaps_before": 0,
        "inbound_fallbacks_added": 0,
        "outbound_fallbacks_added": 0,
        "inbound_unfillable": 0,
        "outbound_unfillable": 0,
    }

    if cleaned_df is None or cleaned_df.empty:
        return recommendations, stats

    # All URLs in the cleaned crawl
    all_urls = set(cleaned_df["Source"].dropna().unique()) | set(cleaned_df["Destination"].dropna().unique())
    all_urls = {u for u in all_urls if isinstance(u, str)}
    stats["total_urls"] = len(all_urls)
    if not all_urls:
        return recommendations, stats

    # Existing crawl link counts
    crawl_inbound: Counter[str] = Counter(cleaned_df["Destination"].dropna().tolist())
    crawl_outbound: Counter[str] = Counter(cleaned_df["Source"].dropna().tolist())

    # Recommendation link counts
    rec_inbound: Counter[str] = Counter(r.get("target_url", "") for r in recommendations)
    rec_outbound: Counter[str] = Counter(r.get("source_url", "") for r in recommendations)

    # Cocoon membership lookups
    cocoon_by_url: dict[str, list[str]] = {}
    code_page_by_op: dict[str, str | None] = {}
    review_page_by_op: dict[str, str | None] = {}
    for cocoon in cocoons:
        op = cocoon.get("operator", "")
        if not op:
            continue
        if cocoon.get("code_page"):
            code_page_by_op[op] = cocoon["code_page"]
        for url in cocoon.get("pages", []):
            cocoon_by_url.setdefault(url, []).append(op)
            ptype = cocoon.get("page_types", {}).get(url) or page_type_lookup.get(url)
            if ptype == "review" and op not in review_page_by_op:
                review_page_by_op[op] = url

    site_reviews = [
        url for cocoon in cocoons
        for url, ptype in cocoon.get("page_types", {}).items()
        if ptype == "review"
    ]
    homepage = _detect_homepage(all_urls)
    all_urls_list = sorted(all_urls)

    # Identify gaps
    inbound_gaps: list[str] = []
    outbound_gaps: list[str] = []
    for url in all_urls:
        final_in = crawl_inbound.get(url, 0) + rec_inbound.get(url, 0)
        final_out = crawl_outbound.get(url, 0) + rec_outbound.get(url, 0)
        if final_in == 0:
            inbound_gaps.append(url)
        if final_out == 0:
            outbound_gaps.append(url)
    stats["inbound_gaps_before"] = len(inbound_gaps)
    stats["outbound_gaps_before"] = len(outbound_gaps)

    # Fill inbound gaps
    fallback_recs: list[dict] = []
    for url in inbound_gaps:
        source, reason = _pick_inbound_fallback(
            url, cocoon_by_url, code_page_by_op, review_page_by_op,
            site_reviews, all_urls_list, homepage,
        )
        if not source:
            stats["inbound_unfillable"] += 1
            continue
        fallback_recs.append({
            "source_url": source,
            "target_url": url,
            "suggested_anchor": _anchor_from_url(url),
            "reason": f"[Coverage fallback] Inbound coverage filler — {reason}.",
            "priority": "medium",
            "relevance_score": 35,
            "is_coverage_fallback": True,
            "coverage_direction": "inbound",
        })
        stats["inbound_fallbacks_added"] += 1

    # Fill outbound gaps
    for url in outbound_gaps:
        target, reason = _pick_outbound_fallback(
            url, cocoon_by_url, code_page_by_op, review_page_by_op,
            site_reviews, all_urls_list, homepage,
        )
        if not target:
            stats["outbound_unfillable"] += 1
            continue
        fallback_recs.append({
            "source_url": url,
            "target_url": target,
            "suggested_anchor": _anchor_from_url(target),
            "reason": f"[Coverage fallback] Outbound coverage filler — {reason}.",
            "priority": "medium",
            "relevance_score": 35,
            "is_coverage_fallback": True,
            "coverage_direction": "outbound",
        })
        stats["outbound_fallbacks_added"] += 1

    return recommendations + fallback_recs, stats
