"""Orphan guarantee pass (Rule 2 — ABSOLUTE).

After the AI returns recommendations, ensure EVERY orphan and true-orphan page
has at least one inbound link recommendation. If the AI missed an orphan, add a
fallback link from the most relevant available source (chain: same-cocoon
review → cocoon review of any kind → site-wide review hub → root URL).
"""

from __future__ import annotations

from urllib.parse import urlparse


def _root_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return None


def _pick_fallback_source(
    target_url: str,
    target_ctx: dict,
    cocoons: list[dict],
    page_type_lookup: dict[str, str],
    cocoon_by_url: dict[str, list[str]],
) -> tuple[str | None, str]:
    """Pick the best available source page to link FROM into the orphan target.

    Returns (source_url, reason). Tries this chain:
      1. Operator review page in same cocoon as the target
      2. Code page in same cocoon as the target
      3. Any review-type page across all cocoons (site authority hub)
      4. Root URL (homepage) — last resort
    """
    target_cocoons = cocoon_by_url.get(target_url, [])

    # 1 + 2: same-cocoon hub
    for cocoon in cocoons:
        if cocoon.get("operator") not in target_cocoons:
            continue
        # Try review page first
        for url, ptype in cocoon.get("page_types", {}).items():
            if url == target_url:
                continue
            if ptype == "review":
                return url, "same-cocoon review (fallback)"
        # Then code page
        code = cocoon.get("code_page")
        if code and code != target_url:
            return code, "same-cocoon code page (fallback)"

    # 3: any review across cocoons
    for cocoon in cocoons:
        for url, ptype in cocoon.get("page_types", {}).items():
            if url == target_url:
                continue
            if ptype == "review":
                return url, "site-wide review hub (fallback)"

    # 4: homepage
    root = _root_url(target_url)
    if root and root != target_url:
        return root, "homepage (last-resort fallback)"

    return None, "no fallback source available"


def ensure_orphan_coverage(
    recommendations: list[dict],
    contexts: list[dict],
    cocoons: list[dict],
    page_type_lookup: dict[str, str],
) -> tuple[list[dict], dict]:
    """Add fallback recommendations for any orphan/true-orphan with zero coverage.

    Returns (recommendations_with_fallbacks, stats).
    """
    # Targets already covered by AI
    covered_targets: set[str] = {rec["target_url"] for rec in recommendations}

    # Build cocoon-by-url lookup
    cocoon_by_url: dict[str, list[str]] = {}
    for cocoon in cocoons:
        op = cocoon.get("operator", "")
        for url in cocoon.get("pages", []):
            cocoon_by_url.setdefault(url, []).append(op)

    # Find orphans missing recommendations
    orphans_missing: list[dict] = []
    for ctx in contexts:
        if not (ctx.get("is_orphan") or ctx.get("is_true_orphan")):
            continue
        if ctx["url"] in covered_targets:
            continue
        orphans_missing.append(ctx)

    fallback_recs: list[dict] = []
    for ctx in orphans_missing:
        target_url = ctx["url"]
        source_url, reason = _pick_fallback_source(
            target_url, ctx, cocoons, page_type_lookup, cocoon_by_url
        )
        if not source_url:
            continue

        anchor = ctx.get("target_keyword") or "read more"
        rec = {
            "source_url": source_url,
            "target_url": target_url,
            "suggested_anchor": anchor,
            "reason": f"[Orphan target] Fallback link added by orphan guarantee pass — {reason}.",
            "priority": "high",
            "relevance_score": 40,  # threshold value — fallback is acceptable, not optimal
            "is_fallback": True,
        }
        fallback_recs.append(rec)

    stats = {
        "orphans_missing_before": len(orphans_missing),
        "fallback_links_added": len(fallback_recs),
    }
    return recommendations + fallback_recs, stats
