"""Link budget caps and selection priority (Rules 12 + 13).

Applies page-type-aware outbound caps per source, an inbound cap per target,
and a deterministic selection priority when candidates exceed the budget.
"""

from __future__ import annotations

# Outbound cap per source page, by page type (Rule 12)
OUTBOUND_CAP_BY_TYPE: dict[str, int] = {
    "comparator": 8,
    "topic-evergreen": 5,
    "topic-event-timely": 3,
    "topic-news": 3,
    "topic-tips-predictions": 3,
    "review": 4,
    "casino-review": 4,
    "poker-review": 4,
    "code": 2,
    "bonus": 2,
    "casino-bonus": 2,
}
DEFAULT_OUTBOUND_CAP = 5

# Inbound cap per target page (Rule 12)
INBOUND_CAP = 10


def _outbound_cap(source_type: str | None) -> int:
    if source_type and source_type in OUTBOUND_CAP_BY_TYPE:
        return OUTBOUND_CAP_BY_TYPE[source_type]
    return DEFAULT_OUTBOUND_CAP


def _selection_priority(rec: dict, target_meta: dict) -> tuple:
    """Sort key — lower tuple = higher priority (selected first).

    Rule 13 order:
      1. Orphan target first
      2. Priority URL target (lowest current inbound count first)
      3. Lowest target PageRank (biggest juice gain)
      4. Highest semantic relevance (tiebreaker)
    """
    is_orphan = bool(target_meta.get("is_orphan") or target_meta.get("is_true_orphan"))
    is_priority = bool(target_meta.get("is_priority"))
    inbound = target_meta.get("inbound_count", 0)
    pagerank = target_meta.get("pagerank", 0.0)
    relevance = rec.get("relevance_score", 0)

    return (
        0 if is_orphan else 1,
        0 if is_priority else 1,
        inbound,           # ascending — lower needs more
        pagerank,          # ascending — lower gets bigger gain
        -relevance,        # higher relevance first
    )


def apply_link_budgets(
    recommendations: list[dict],
    page_type_lookup: dict[str, str],
    contexts_by_url: dict[str, dict],
) -> tuple[list[dict], dict]:
    """Filter recommendations to respect outbound/inbound caps.

    Returns (kept_recommendations, stats).
    """
    # Group recommendations by source then sort by selection priority
    by_source: dict[str, list[dict]] = {}
    for rec in recommendations:
        by_source.setdefault(rec["source_url"], []).append(rec)

    inbound_used: dict[str, int] = {}
    kept: list[dict] = []
    dropped_outbound = 0
    dropped_inbound = 0

    for source_url, recs in by_source.items():
        source_type = page_type_lookup.get(source_url)
        cap = _outbound_cap(source_type)

        # Sort by selection priority
        recs_sorted = sorted(
            recs,
            key=lambda r: _selection_priority(r, contexts_by_url.get(r["target_url"], {})),
        )

        kept_for_source = 0
        for rec in recs_sorted:
            if kept_for_source >= cap:
                dropped_outbound += 1
                continue
            tgt = rec["target_url"]
            if inbound_used.get(tgt, 0) >= INBOUND_CAP:
                dropped_inbound += 1
                continue
            kept.append(rec)
            inbound_used[tgt] = inbound_used.get(tgt, 0) + 1
            kept_for_source += 1

    stats = {
        "kept": len(kept),
        "dropped_outbound": dropped_outbound,
        "dropped_inbound": dropped_inbound,
        "total_in": len(recommendations),
    }
    return kept, stats
