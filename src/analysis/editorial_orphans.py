"""Editorial-orphan detection.

A page is *editorially orphaned* when it had inbound internal links in the
parsed crawl but ZERO survive after the Step 2 exclusions (pagination /
template / news / manual). In other words: no genuine editorial content page
links to it — its only inbound came from archive-pagination pages, the
site-wide template (nav/footer), timely/news pages, or manually-excluded
URLs, all of which were (correctly) stripped before analysis.

This is distinct from:
  - a *true orphan* — never had any inbound link at all (needs the Full Site
    URL List upload to be detected),
  - a *broken page* — correctly removed because it returns 3xx/4xx/5xx.

Editorially-orphaned pages are real 200-OK content that needs editorial
inbound links. They tend to vanish silently from the analysis because, once
their only inbound sources are excluded, they can drop out of the link graph
entirely. This module surfaces them so the team can add real links.
"""
from __future__ import annotations

import pandas as pd


def detect_editorial_orphans(
    pre_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    pagination_urls: set[str] | None = None,
    news_urls: set[str] | None = None,
    manual_urls: set[str] | None = None,
    broken_targets: set[str] | None = None,
    max_sources_listed: int = 12,
) -> list[dict]:
    """Find content pages that lost ALL inbound links to Step 2 exclusions.

    Args:
        pre_df: edges BEFORE Step 2 exclusions (still contains pagination /
            template / news edges). Must have Source + Destination columns.
        cleaned_df: edges AFTER all Step 2 exclusions.
        pagination_urls / news_urls / manual_urls: the page-level exclusion
            sets, used both to skip the excluded pages themselves and to
            classify *why* each lost inbound source went away.
        broken_targets: pages removed for being 3xx/4xx/5xx — skipped (they're
            handled by the removal engine, not here).
        max_sources_listed: cap on how many lost-source URLs to attach per row.

    Returns:
        One dict per orphaned page, sorted by lost-inbound count desc:
        {url, lost_inbound, lost_sources, pagination_only, reason}
    """
    pagination_urls = pagination_urls or set()
    news_urls = news_urls or set()
    manual_urls = manual_urls or set()
    broken_targets = broken_targets or set()
    excluded_pages = pagination_urls | news_urls | manual_urls | broken_targets

    if pre_df is None or len(pre_df) == 0 or "Destination" not in pre_df.columns:
        return []

    # One pass: map each destination to the list of its inbound source URLs.
    src_by_dest = (
        pre_df.dropna(subset=["Destination", "Source"])
        .groupby("Destination")["Source"]
        .apply(list)
        .to_dict()
    )
    survivors = (
        set(cleaned_df["Destination"].dropna().unique())
        if cleaned_df is not None and len(cleaned_df)
        else set()
    )

    out: list[dict] = []
    for page, sources in src_by_dest.items():
        if not page:
            continue
        if page in survivors:
            continue  # still has at least one surviving editorial inbound link
        if page in excluded_pages:
            continue  # the page itself was excluded (pagination/news/manual/broken)

        # Distinct sources, preserving order, excluding self-references.
        distinct = [s for s in dict.fromkeys(sources) if s and s != page]
        if not distinct:
            continue

        n_pag = sum(1 for s in distinct if s in pagination_urls)
        n_news = sum(1 for s in distinct if s in news_urls)
        n_other = len(distinct) - n_pag - n_news
        pagination_only = n_pag == len(distinct)

        parts: list[str] = []
        if n_pag:
            parts.append(f"{n_pag} from pagination/archive pages")
        if n_news:
            parts.append(f"{n_news} from news/timely pages")
        if n_other:
            parts.append(f"{n_other} from template/menu or excluded pages")
        reason = (
            "All inbound came from excluded sources ("
            + ", ".join(parts)
            + "). No editorial content page links here."
        )

        out.append({
            "url": page,
            "lost_inbound": int(len(sources)),
            "lost_sources": distinct[:max_sources_listed],
            "pagination_only": pagination_only,
            "reason": reason,
        })

    # Pagination-only pages first (clearest signal), then by lost-inbound volume.
    out.sort(key=lambda d: (not d["pagination_only"], -d["lost_inbound"]))
    return out
