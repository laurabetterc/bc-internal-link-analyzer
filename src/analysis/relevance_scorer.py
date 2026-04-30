"""Semantic relevance scoring for candidate link pairs.

Implements the hybrid model from docs/linking-rules.md section 5:
- Hard filters discard invalid pairs (cross-cocoon, existing link, self-link, market mismatch)
- Soft scoring 0-100 across signals (cocoon, URL tokens, intent match, keyword, anchors)
- Cocoon proximity overrides intra-cocoon scoring with cluster-based logic
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Page-type clusters (Rule 7 / section 3 of linking-rules.md)
# --------------------------------------------------------------------------- #

CLUSTERS: dict[str, set[str]] = {
    "bonus": {"code", "bonus", "casino-bonus", "registration", "vip-program"},
    "mobile": {"app", "streaming"},
    "money": {"payment", "cashout"},
    "sports-betting": {"odds", "sport-specific", "streaming"},
    "casino": {"slots", "live-casino", "table-games", "jackpots"},
    "poker": {"cash-games", "tournaments", "freerolls"},
    "trust": {"review", "customer-service", "license-info", "responsible-gambling"},
    "editorial": {"topic-evergreen", "topic-event-timely", "topic-news", "topic-tips-predictions"},
}

CANONICAL_TYPES: set[str] = set().union(*CLUSTERS.values()) | {
    "casino-review", "poker-review", "esports", "virtual-sports",
    "horse-racing", "lottery", "bingo", "fantasy", "region-specific", "comparator",
}


def _cluster_of(page_type: str | None) -> str | None:
    if not page_type:
        return None
    for cluster, types in CLUSTERS.items():
        if page_type in types:
            return cluster
    return None


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #

_TOKEN_SPLIT = re.compile(r"[\W_]+", re.UNICODE)


def _path_tokens(url: str) -> set[str]:
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return set()
    tokens = {t for t in _TOKEN_SPLIT.split(path) if t and len(t) > 1 and not t.isdigit()}
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------- #
# Cocoon proximity (intra-cocoon)
# --------------------------------------------------------------------------- #

def _cocoon_proximity_score(
    source_type: str | None,
    target_type: str | None,
    target_is_code: bool,
    target_is_review: bool,
) -> int:
    """Cluster-based proximity score within the same cocoon (0-100)."""
    if target_is_review:
        return 80
    if target_is_code:
        return 70

    src_cluster = _cluster_of(source_type)
    tgt_cluster = _cluster_of(target_type)

    # Same cluster
    if src_cluster and tgt_cluster and src_cluster == tgt_cluster:
        return 90

    # Custom (niche) types
    if source_type and source_type not in CANONICAL_TYPES and target_type and target_type not in CANONICAL_TYPES:
        return 100 if source_type == target_type else 50

    # Adjacent clusters (heuristic — anything with a cluster but not same)
    if src_cluster and tgt_cluster:
        return 60

    # Fallback
    return 40


# --------------------------------------------------------------------------- #
# Main scorer
# --------------------------------------------------------------------------- #

def score_pair(
    source_url: str,
    target_url: str,
    source_ctx: dict | None,
    target_ctx: dict | None,
    source_cocoons: list[str],
    target_cocoons: list[str],
    source_type: str | None,
    target_type: str | None,
    target_code_page: str | None,
    target_review_page: str | None,
    existing_links: set[tuple[str, str]],
    target_keyword: str | None,
    target_inbound_anchors: list[str] | None,
    is_multi_operator_source: bool = False,
    target_is_past_event: bool = False,
    source_section: str | None = None,
    target_section: str | None = None,
    source_market: str | None = None,
    target_market: str | None = None,
) -> dict:
    """Score a candidate (source, target) pair.

    Returns a dict {"score": int, "passed": bool, "reason": str}.
    Hard filters discard the pair entirely (passed=False, score=0).

    `source_section` / `target_section`: ISO 639-1 or 3166-1 code for the
    URL section (e.g. "it", "mx"). When both are set and differ, the pair
    is blocked (B6 — defense-in-depth alongside the Phase A cleaning filter).

    `source_market` / `target_market`: market code from
    `market_detector.market_for_url`. When both are set and differ, blocked
    (Phase 10 backlog — per-link market filtering, complements the start-of-run
    market gate).
    """
    # ----- Hard filters -----
    if source_url == target_url:
        return {"score": 0, "passed": False, "reason": "self-link"}

    if (source_url, target_url) in existing_links:
        return {"score": 0, "passed": False, "reason": "link already exists"}

    # B6: cross-section (language / country) link blocked. Only enforced when
    # BOTH sides have a recognized section code — None means root / no prefix,
    # which is fine to link from/to a specific section in some BC layouts.
    if source_section and target_section and source_section != target_section:
        return {
            "score": 0,
            "passed": False,
            "reason": f"cross-section link blocked (/{source_section}/ → /{target_section}/)",
        }

    # Phase 10 backlog: cross-market link blocked. Same rule shape as B6 but
    # uses the market_detector signals (TLD, geo subdomain, market subfolder).
    if source_market and target_market and source_market != target_market:
        return {
            "score": 0,
            "passed": False,
            "reason": f"cross-market link blocked ({source_market} → {target_market})",
        }

    # Cross-cocoon: only allowed if source is a multi-operator page
    if source_cocoons and target_cocoons:
        same_cocoon = bool(set(source_cocoons) & set(target_cocoons))
        if not same_cocoon and not is_multi_operator_source:
            return {"score": 0, "passed": False, "reason": "cross-cocoon link not allowed"}

    # ----- Soft scoring -----
    score = 0

    # +40 same cocoon (or multi-op source covers target cocoon)
    if source_cocoons and target_cocoons and (set(source_cocoons) & set(target_cocoons)):
        score += 40
    elif is_multi_operator_source and target_cocoons:
        # Multi-op source linking to a cocoon it covers
        score += 40

    # Intra-cocoon proximity (replaces URL-token scoring within same cocoon)
    in_same_cocoon = bool(source_cocoons and target_cocoons and (set(source_cocoons) & set(target_cocoons)))
    if in_same_cocoon:
        score += _cocoon_proximity_score(
            source_type=source_type,
            target_type=target_type,
            target_is_code=(target_url == target_code_page),
            target_is_review=(target_type == "review" or target_url == target_review_page),
        ) // 5  # scale 0-100 → 0-20 to fit the 20-point URL-token slot
    else:
        # +20 URL token overlap (Jaccard)
        overlap = _jaccard(_path_tokens(source_url), _path_tokens(target_url))
        score += int(overlap * 20)

    # +20 content-type intent match (handled by AI/Rule 11) — credit when comparator → matching type
    if source_type == "comparator" and target_type and target_type != "comparator":
        score += 20

    # +10 target keyword in source slug or anchors
    if target_keyword:
        kw_tokens = {t for t in _TOKEN_SPLIT.split(target_keyword.lower()) if len(t) > 2}
        src_tokens = _path_tokens(source_url)
        if kw_tokens and (kw_tokens & src_tokens):
            score += 10

    # +10 anchor topical match — source's URL tokens overlap with target's existing inbound anchors
    if target_inbound_anchors:
        anchor_tokens: set[str] = set()
        for anchor in target_inbound_anchors[:10]:
            anchor_tokens.update(t for t in _TOKEN_SPLIT.split(anchor.lower()) if len(t) > 2)
        if anchor_tokens and (anchor_tokens & _path_tokens(source_url)):
            score += 10

    # Rule 17 — past-event (one-time) decay penalty as target
    if target_is_past_event:
        score -= 30

    score = max(0, min(100, score))
    passed = score >= 40

    return {
        "score": score,
        "passed": passed,
        "reason": "scored" if passed else f"below threshold (score={score})",
    }
