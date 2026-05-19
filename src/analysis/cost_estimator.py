"""Pre-run cost estimate for the AI pipeline (Phase 11 / A3).

Empirical estimates derived from the 2026-04-29 cost incident:
  500 pages on `gemini-3.1-pro-preview` (forced thinking) ≈ $14 → ~$0.028 per page.

Other models scale roughly linearly via the input/output token price ratio. Treat the
output as a planning aid — actual cost can vary ±30% depending on cocoon density and
how many pages the AI flags as multi-operator. The point of the gate is order-of-magnitude
clarity ($0.50 vs $14), not 3-decimal precision.
"""

from __future__ import annotations

import math

from src import config as _config


# Per-page USD cost, derived from real runs.
# - Pro Preview anchored on the 2026-04-29 incident: $14 / 500 pages = $0.028/page.
# - Flash-Lite anchored on bolavip MX (Session 22): $0.018 / 166 contexts ≈
#   $0.0001/page. Set to $0.00025 (50% safety buffer) so the panel rounds up,
#   never down. The old $0.0042 figure was a theoretical Pro/Lite ratio that
#   didn't survive contact with `thinking_level="low"` on Flash-Lite.
# - Flash 3 / 2.5 Flash kept at theoretical ratios — recalibrate when we get
#   real measurements.
_COST_PER_PAGE: dict[str, float] = {
    "gemini-3.1-pro-preview": 0.028,
    "gemini-3.1-flash-lite-preview": 0.00025,
    "gemini-3-flash-preview": 0.005,
    "gemini-2.5-flash": 0.002,
}

# Legacy default; the active cap is dynamic via `_config.max_ai_pages()`.
PAGE_CAP = 500


def estimate_working_set_size(
    page_count: int,
    priority_count: int = 0,
    orphan_count: int = 0,
    true_orphan_count: int = 0,
    max_pages: int | None = None,
) -> int:
    """Approximate `prepare_page_contexts` output size without needing PageRank.

    The AI doesn't run on every cleaned page. `prepare_page_contexts` selects
    priority + top-50 PageRank + orphans + true_orphans, then expands by ~5
    neighbors per "interesting" page, capped at 500. This helper mirrors that
    selection using only the data available before the run (PR substituted by
    a top-50 reservation). Replaces the old `min(page_count, 500)` ceiling
    that overshot 65x on bolavip MX (271 cleaned pages → 166 contexts → $1.18
    estimate vs. $0.018 actual).
    """
    if page_count <= 0:
        return 0
    if max_pages is None:
        max_pages = _config.max_ai_pages()
    top_pr_assumed = min(50, page_count)
    interesting_core = priority_count + orphan_count + true_orphan_count + top_pr_assumed
    # ~30% overlap between priority / orphans / top-PR on real data
    interesting = max(top_pr_assumed, int(interesting_core * 0.7))
    interesting = min(interesting, page_count)
    # `prepare_page_contexts` expands by up to 10 neighbors per interesting
    # page (5 inbound + 5 outbound), but dedup typically retains ~1.5x.
    # Calibrated against bolavip MX (estimate 160 vs actual 166 contexts).
    neighbors = min(int(interesting * 1.5), page_count - interesting)
    estimated = interesting + max(0, neighbors)
    return min(estimated, max_pages, page_count)


def _resolve_per_page(model: str) -> tuple[float, bool]:
    """Look up the per-page cost for a model. Returns (cost, is_known_model)."""
    if model in _COST_PER_PAGE:
        return _COST_PER_PAGE[model], True
    # Heuristic for unknown / future models: prefix match on family.
    name = model.lower()
    if "lite" in name:
        return _COST_PER_PAGE["gemini-3.1-flash-lite-preview"], False
    if "pro" in name:
        return _COST_PER_PAGE["gemini-3.1-pro-preview"], False
    if "flash" in name:
        return _COST_PER_PAGE["gemini-3-flash-preview"], False
    # Fallback: assume Flash-Lite economics so we don't wildly over-quote.
    return _COST_PER_PAGE["gemini-3.1-flash-lite-preview"], False


def estimate_cost(
    page_count: int,
    model: str | None = None,
    cocoon_model: str | None = None,
    working_set_size: int | None = None,
) -> dict:
    """Estimate the USD cost of running the AI pipeline.

    `model` is the recommendation-call model (the user's pick).
    `cocoon_model` (C1 routing) is the cocoon-classification model — defaults
    to Flash-Lite when the recommendation model is more expensive, matching
    the runtime behavior of `ai_analyzer._cocoon_model()`.

    `working_set_size` is the AI's actual contexts-subset size (output of
    `estimate_working_set_size`). When provided, cost is computed against
    this subset instead of `min(page_count, PAGE_CAP)` — fixes the 65x
    overcount on small sites where the working set is much smaller than
    the cleaned page count.

    Cost is split between cocoon and recommendation batches by call share,
    so picking Pro for recommendations no longer pays the Pro premium on
    the cocoon-classification work.

    Returns dict with:
        page_count, capped_pages, model, cocoon_model, cost_per_page,
        total_cost, cocoon_batches, recommendation_batches, total_calls,
        is_known_model, routed (bool — true when cocoon != rec model)
    """
    model = model or _config.GEMINI_MODEL
    if cocoon_model is None:
        # Default routing matches ai_analyzer._cocoon_model() exactly.
        name = (model or "").lower()
        if "flash-lite" in name or "2.5-flash" in name:
            cocoon_model = model
        else:
            cocoon_model = "gemini-3.1-flash-lite-preview"

    cap_now = _config.max_ai_pages()
    if working_set_size is not None:
        capped = max(0, min(working_set_size, page_count, cap_now))
    else:
        capped = min(page_count, cap_now)
    per_page_rec, is_known_rec = _resolve_per_page(model)
    per_page_cocoon, is_known_cocoon = _resolve_per_page(cocoon_model)

    cocoon_batches = max(1, math.ceil(capped / _config.AI_COCOON_BATCH_SIZE)) if capped else 0

    # B3 — when closed-task scoring is active, recommendation calls batch by
    # candidate count (filtered pairs), not by page count. Anchor: bolavip MX
    # had 4,980 raw → 2,633 filtered candidates on 166 contexts → ~16 filtered
    # candidates per source. Use that as the heuristic to estimate score
    # batches; falls back to the legacy page-batched count when closed-task
    # is off.
    closed_task_active = _config.ILA_USE_EMBEDDINGS and _config.ILA_USE_CLOSED_TASK
    if closed_task_active and capped > 0:
        est_filtered_candidates = capped * 15  # empirical anchor (Session 22)
        rec_batches = max(
            1,
            math.ceil(est_filtered_candidates / _config.AI_SCORE_BATCH_SIZE),
        )
    else:
        rec_batches = max(1, math.ceil(capped / _config.AI_BATCH_SIZE)) if capped else 0
    total_calls = cocoon_batches + rec_batches

    if total_calls > 0 and capped > 0:
        cocoon_share = cocoon_batches / total_calls
        rec_share = rec_batches / total_calls
        # Blended per-page cost across the two tiers.
        blended_per_page = (cocoon_share * per_page_cocoon) + (rec_share * per_page_rec)
    else:
        blended_per_page = per_page_rec

    total_cost = capped * blended_per_page

    # B1 — embedding shortlist cost. gemini-embedding-001 prices at ~$0.000025
    # per 1K input tokens. ~30 tokens per page text -> ~$0.00075 per 1K pages.
    # Negligible vs recommendation cost; surfaced separately so the user can
    # see the full pipeline cost when the feature is on.
    embedding_cost = 0.0
    if _config.ILA_USE_EMBEDDINGS and capped > 0:
        embedding_cost = capped * 0.00000075  # ~$0.00075 per 1000 pages

    return {
        "page_count": page_count,
        "capped_pages": capped,
        "model": model,
        "cocoon_model": cocoon_model,
        "cost_per_page": blended_per_page,
        "total_cost": total_cost + embedding_cost,
        "recommendation_cost": total_cost,
        "embedding_cost": embedding_cost,
        "embeddings_enabled": _config.ILA_USE_EMBEDDINGS,
        "cocoon_batches": cocoon_batches,
        "recommendation_batches": rec_batches,
        "total_calls": total_calls,
        "is_known_model": is_known_rec and is_known_cocoon,
        "routed": cocoon_model != model,
        "page_cap_applied": capped < page_count,
    }


def format_cost(cost: float) -> str:
    """Render a USD cost with sensible precision for the UI gate."""
    if cost < 0.01:
        return "<$0.01"
    if cost < 1:
        return f"${cost:.2f}"
    if cost < 10:
        return f"${cost:.2f}"
    return f"${cost:.0f}"
