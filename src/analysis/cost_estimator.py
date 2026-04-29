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
) -> dict:
    """Estimate the USD cost of running the AI pipeline.

    page_count is the number of unique pages remaining after Step 2 exclusions
    (we do NOT pre-apply the page cap here — the function reports both the raw
    page count and the capped count so the UI can explain the cap).

    Returns dict with:
        page_count, capped_pages, model, cost_per_page, total_cost,
        cocoon_batches, recommendation_batches, total_calls, is_known_model
    """
    model = model or _config.GEMINI_MODEL
    capped = min(page_count, PAGE_CAP)
    per_page, is_known = _resolve_per_page(model)

    cocoon_batches = max(1, math.ceil(capped / _config.AI_COCOON_BATCH_SIZE)) if capped else 0
    rec_batches = max(1, math.ceil(capped / _config.AI_BATCH_SIZE)) if capped else 0

    total_cost = capped * per_page
    return {
        "page_count": page_count,
        "capped_pages": capped,
        "model": model,
        "cost_per_page": per_page,
        "total_cost": total_cost,
        "cocoon_batches": cocoon_batches,
        "recommendation_batches": rec_batches,
        "total_calls": cocoon_batches + rec_batches,
        "is_known_model": is_known,
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
