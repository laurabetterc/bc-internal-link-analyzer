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


# Per-page USD cost, derived from real runs. Pro Preview is the anchor point ($14/500 pages).
# Lite/Flash ratios match the public input/output prices and the smaller thinking footprint.
_COST_PER_PAGE: dict[str, float] = {
    "gemini-3.1-pro-preview": 0.028,
    "gemini-3.1-flash-lite-preview": 0.0042,
    "gemini-3-flash-preview": 0.009,
    "gemini-2.5-flash": 0.005,
}

# Cap mirrors the AI pipeline's `max_pages` selection in ai_analyzer._build_page_contexts.
PAGE_CAP = 500


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
) -> dict:
    """Estimate the USD cost of running the AI pipeline.

    `model` is the recommendation-call model (the user's pick).
    `cocoon_model` (C1 routing) is the cocoon-classification model — defaults
    to Flash-Lite when the recommendation model is more expensive, matching
    the runtime behavior of `ai_analyzer._cocoon_model()`.

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

    capped = min(page_count, PAGE_CAP)
    per_page_rec, is_known_rec = _resolve_per_page(model)
    per_page_cocoon, is_known_cocoon = _resolve_per_page(cocoon_model)

    cocoon_batches = max(1, math.ceil(capped / _config.AI_COCOON_BATCH_SIZE)) if capped else 0
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
    return {
        "page_count": page_count,
        "capped_pages": capped,
        "model": model,
        "cocoon_model": cocoon_model,
        "cost_per_page": blended_per_page,
        "total_cost": total_cost,
        "cocoon_batches": cocoon_batches,
        "recommendation_batches": rec_batches,
        "total_calls": total_calls,
        "is_known_model": is_known_rec and is_known_cocoon,
        "routed": cocoon_model != model,
        "page_cap_applied": page_count > PAGE_CAP,
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
