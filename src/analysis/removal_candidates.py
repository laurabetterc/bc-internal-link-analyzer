"""Removal-candidate detection — closes the original PRD's `to remove` status.

The original PRD specced 3 link statuses (`live`, `to add`, `to remove`) but
`to remove` was never implemented. This module surfaces existing crawl links
that should be reviewed for removal, using two deterministic heuristics
(no AI calls):

1. **Hard-fail removals**: existing links that fail `score_pair` hard rules
   — cross-cocoon for a single-operator source, cross-section, cross-market,
   or target that's a past-event timely page. These violate the linking
   policy regardless of budget pressure.

2. **Budget-pressure swaps**: when a source page's combined `live + to_add`
   count exceeds its page-type outbound cap (`link_budget.OUTBOUND_CAP_BY_TYPE`),
   the lowest-scoring existing links are surfaced as swap candidates — but
   ONLY when a "to add" rec on the same source has a higher relevance score.
   We never auto-execute; the SEO Content Manager reviews and decides.

Output integrates with the existing CSV / HTML export plumbing via a new
`to remove` Status value plus a `removal_type` field for filtering.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.event_detection import is_past_event
from src.analysis.market_detector import market_for_url
from src.analysis.relevance_scorer import score_pair
from src.cleaning.language import extract_lang_segment


def _build_lookups(cocoons: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Build the per-URL cocoon membership / code-page / review-page lookups."""
    operators_for_url: dict[str, list[str]] = {}
    code_page_by_url: dict[str, str | None] = {}
    review_page_by_op: dict[str, str | None] = {}
    for cocoon in cocoons:
        op = cocoon.get("operator", "")
        code = cocoon.get("code_page")
        for url in cocoon.get("pages", []):
            operators_for_url.setdefault(url, []).append(op)
            if url not in code_page_by_url:
                code_page_by_url[url] = code
            if cocoon.get("page_types", {}).get(url) == "review":
                review_page_by_op[op] = url
    multi_operator_urls = (cocoons[0].get("_multi_operator_urls", {}) if cocoons else {})
    return operators_for_url, code_page_by_url, review_page_by_op, multi_operator_urls


def compute_removal_candidates(
    cleaned_df: pd.DataFrame,
    recommendations: list[dict],
    cocoons: list[dict],
    page_type_lookup: dict[str, str],
    contexts_by_url: dict[str, dict],
    broken_links: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    """Identify existing crawl links worth flagging for removal.

    Removal is expensive for the content manager (manual CMS work per link),
    so the bar is intentionally narrow: only flag when a link is genuinely
    broken or sends users to the wrong content. Editorial-but-suboptimal
    links (cross-cocoon, low-score, over-budget) stay live.

    Auto-flagged `to remove`:
      - Cross-section: user lands on wrong-language content
      - Cross-market: user lands on wrong-country content
      - Self-link: useless edge
      - 4xx / 5xx broken targets (from `broken_links`): dead page

    Explicitly NOT flagged (intentional design choice):
      - Cross-cocoon links — often valuable editorial cross-references
      - Below-threshold soft-score links — work fine, just suboptimal
      - Swap candidates (over-budget): the budget cap is a soft target
      - 3xx redirects — link still works for users

    Returns (removal_candidates, stats). Each candidate has the same shape as
    a recommendation plus `removal_type` ("hard_fail" | "broken_target") and
    `relevance_score`.
    """
    broken_target_rows: list[dict] = []
    if broken_links:
        broken_target_rows = _build_broken_target_removals(broken_links)

    if cleaned_df is None or len(cleaned_df) == 0:
        return broken_target_rows, {
            "total": len(broken_target_rows),
            "hard_fail": 0, "swap": 0, "broken_target": len(broken_target_rows),
            "scored_links": 0,
        }

    operators_for_url, code_page_by_url, review_page_by_op, multi_operator_urls = (
        _build_lookups(cocoons)
    )

    # Inbound anchor lookup (per target) — used as a soft signal in score_pair
    inbound_anchors_lookup: dict[str, list[str]] = (
        cleaned_df.groupby("Destination")["Anchor"]
        .apply(lambda x: list({a for a in x if a}))
        .to_dict()
    )

    # Score every unique (source, destination) edge from the crawl. Deduped on
    # (source, dest) since `score_pair` is order-only — anchor variations across
    # parallel edges don't change the score.
    crawl_edges = cleaned_df[["Source", "Destination", "Anchor"]].drop_duplicates(
        subset=["Source", "Destination"]
    )

    hard_fail: list[dict] = []
    crawl_link_scores: dict[tuple[str, str], dict] = {}

    for row in crawl_edges.itertuples(index=False):
        src = row.Source
        tgt = row.Destination
        if not src or not tgt or src == tgt:
            continue
        anchor = getattr(row, "Anchor", "") or ""

        src_ctx = contexts_by_url.get(src)
        tgt_ctx = contexts_by_url.get(tgt)
        src_ops = operators_for_url.get(src, [])
        tgt_ops = operators_for_url.get(tgt, [])
        is_multi_op_src = len(src_ops) > 1 or src in multi_operator_urls
        target_review = next(
            (review_page_by_op[op] for op in tgt_ops if review_page_by_op.get(op)),
            None,
        )

        # Empty existing_links — we want score_pair to evaluate the link itself,
        # not reject it as "already exists".
        scored = score_pair(
            source_url=src,
            target_url=tgt,
            source_ctx=src_ctx,
            target_ctx=tgt_ctx,
            source_cocoons=src_ops,
            target_cocoons=tgt_ops,
            source_type=page_type_lookup.get(src),
            target_type=page_type_lookup.get(tgt),
            target_code_page=code_page_by_url.get(tgt),
            target_review_page=target_review,
            existing_links=set(),
            target_keyword=(tgt_ctx.get("target_keyword") if tgt_ctx else None),
            target_inbound_anchors=inbound_anchors_lookup.get(tgt, []),
            is_multi_operator_source=is_multi_op_src,
            target_is_past_event=is_past_event(
                tgt,
                page_type=page_type_lookup.get(tgt),
                target_keyword=(tgt_ctx.get("target_keyword") if tgt_ctx else None),
            ),
            source_section=extract_lang_segment(src),
            target_section=extract_lang_segment(tgt),
            source_market=market_for_url(src),
            target_market=market_for_url(tgt),
        )

        is_violation = bool(scored.get("is_rule_violation"))
        reason = scored.get("reason", "") or ""
        crawl_link_scores[(src, tgt)] = {
            "score": scored["score"],
            "passed": scored["passed"],
            "reason": reason,
            "is_rule_violation": is_violation,
            "anchor": anchor,
        }

        # Flag only the rule violations the team should actually fix:
        # self-link / cross-section / cross-market. Cross-cocoon links are
        # editorial cross-references — usually intentional, often valuable,
        # not worth the manual CMS work to strip from a 300-site portfolio.
        if not is_violation:
            continue
        if reason.startswith("cross-cocoon"):
            continue
        hard_fail.append({
            "source_url": src,
            "target_url": tgt,
            "anchor": anchor,
            "reason": f"Hard-fail: {reason}",
            "removal_type": "hard_fail",
            "relevance_score": scored["score"],
        })

    # Swap-candidate / over-budget detection used to live here. Removed —
    # forcing the team to swap a low-scoring-but-valid existing link for a
    # marginally-higher-scoring rec creates real CMS work for unclear gain.
    # Recommendations now compete on their own merit; existing links stay
    # unless they're broken or send users to the wrong content.

    all_removals = broken_target_rows + hard_fail
    stats = {
        "total": len(all_removals),
        "hard_fail": len(hard_fail),
        "swap": 0,  # kept in stats for backward-compat with existing UI panels
        "broken_target": len(broken_target_rows),
        "scored_links": len(crawl_link_scores),
    }
    return all_removals, stats


def _build_broken_target_removals(broken_links: list[dict]) -> list[dict]:
    """Convert broken-link edges from the parser into `to remove` rows.

    Only emits rows for 4xx / 5xx targets — the link is dead and the team
    must fix it. 3xx redirects are intentionally skipped: the link still
    works for the user, internal hops cost some crawl budget but updating
    every redirected link is too much CMS work for the marginal gain.

    `broken_links` items: {source_url, target_url, status_code, anchor}.
    Deduped on (source, target) — same edge in parallel crawl rows surfaces
    once.
    """
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    for edge in broken_links:
        code = (edge.get("status_code") or "").strip()
        if not code or code.startswith("3"):
            continue
        src = edge.get("source_url") or ""
        tgt = edge.get("target_url") or ""
        if not src or not tgt or (src, tgt) in seen:
            continue
        seen.add((src, tgt))
        rows.append({
            "source_url": src,
            "target_url": tgt,
            "anchor": edge.get("anchor", ""),
            "reason": f"Broken target: {_advice_for_status(code)}",
            "removal_type": "broken_target",
            "relevance_score": 0,
            "status_code": code,
        })
    return rows


def _advice_for_status(code: str) -> str:
    if code == "404":
        return "Target returns 404 — remove or update link"
    if code.startswith("4"):
        return f"Target returns {code} — remove or update link"
    if code.startswith("5"):
        return f"Target returns {code} (server error) — remove or update link"
    return f"Target returns {code or 'non-200'} — remove or update link"
