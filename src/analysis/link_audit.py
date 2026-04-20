"""Link audit: compute site-wide internal linking statistics."""

import pandas as pd


def compute_link_audit(df: pd.DataFrame, full_url_list: set | None = None) -> dict:
    """Compute internal link statistics from cleaned link data.

    Args:
        df: Cleaned DataFrame with Source and Destination columns.
        full_url_list: Optional set of all site URLs. When provided, URLs in this
            list that don't appear anywhere in the crawl are flagged as "true orphans"
            — pages completely invisible to internal linking.

    Returns:
        Dictionary with audit metrics.
    """
    all_sources = df["Source"].unique()
    all_destinations = df["Destination"].unique()
    all_pages = set(all_sources) | set(all_destinations)

    total_pages = len(all_pages)
    total_links = len(df)

    # Inbound links per page (how many links point TO each page)
    inbound_counts = df.groupby("Destination").size()

    # Pages that appear as source or destination but have zero inbound content links
    pages_with_inbound = set(inbound_counts.index)
    orphan_pages = sorted(all_pages - pages_with_inbound)

    # True orphans: URLs from the full site list that don't appear in the crawl at all
    true_orphan_pages = []
    if full_url_list:
        true_orphan_pages = sorted(full_url_list - all_pages)

    # Merged orphan list — both orphan types unified for presentation.
    # Each entry carries a flag so the UI/export can annotate pages not found in the crawl.
    all_orphan_pages = [{"url": u, "in_crawl": True} for u in orphan_pages] + [
        {"url": u, "in_crawl": False} for u in true_orphan_pages
    ]

    # Outbound links per page (how many links each page sends)
    outbound_counts = df.groupby("Source").size()

    # Per-page stats (inbound)
    inbound_avg = inbound_counts.mean() if len(inbound_counts) > 0 else 0
    inbound_median = inbound_counts.median() if len(inbound_counts) > 0 else 0
    inbound_max = inbound_counts.max() if len(inbound_counts) > 0 else 0
    inbound_min = inbound_counts.min() if len(inbound_counts) > 0 else 0

    # Per-page stats (outbound)
    outbound_avg = outbound_counts.mean() if len(outbound_counts) > 0 else 0
    outbound_median = outbound_counts.median() if len(outbound_counts) > 0 else 0
    outbound_max = outbound_counts.max() if len(outbound_counts) > 0 else 0
    outbound_min = outbound_counts.min() if len(outbound_counts) > 0 else 0

    return {
        "total_pages": total_pages,
        "total_links": total_links,
        "orphan_count": len(orphan_pages),
        "orphan_pages": orphan_pages,
        "true_orphan_count": len(true_orphan_pages),
        "true_orphan_pages": true_orphan_pages,
        "all_orphan_count": len(orphan_pages) + len(true_orphan_pages),
        "all_orphan_pages": all_orphan_pages,
        "inbound_avg": round(inbound_avg, 1),
        "inbound_median": round(inbound_median, 1),
        "inbound_max": int(inbound_max),
        "inbound_min": int(inbound_min),
        "outbound_avg": round(outbound_avg, 1),
        "outbound_median": round(outbound_median, 1),
        "outbound_max": int(outbound_max),
        "outbound_min": int(outbound_min),
        "inbound_counts": inbound_counts,
        "outbound_counts": outbound_counts,
    }


def get_priority_urls_health(
    df: pd.DataFrame,
    priority_df: pd.DataFrame,
    pagerank_scores: dict | None = None,
    critical_max: int = 2,
    warning_max: int = 7,
) -> pd.DataFrame:
    """Evaluate health of priority URLs based on inbound link counts.

    Args:
        df: Cleaned link data.
        priority_df: Priority URLs with URL, Target Keyword, Content Type.
        pagerank_scores: Optional dict of {url: pagerank_score}.
        critical_max: Max inbound links for "critical" status.
        warning_max: Max inbound links for "warning" status.

    Returns:
        DataFrame with priority URL health info.
    """
    inbound_counts = df.groupby("Destination").size()

    rows = []
    for _, row in priority_df.iterrows():
        url = row["URL"]
        inbound = int(inbound_counts.get(url, 0))

        if inbound <= critical_max:
            health = "critical"
        elif inbound <= warning_max:
            health = "warning"
        else:
            health = "good"

        entry = {
            "URL": url,
            "Target Keyword": row["Target Keyword"],
            "Content Type": row.get("Content Type", ""),
            "Inbound Links": inbound,
            "Health": health,
        }

        if pagerank_scores is not None:
            entry["PageRank"] = pagerank_scores.get(url, 0.0)

        rows.append(entry)

    result = pd.DataFrame(rows)
    # Sort: critical first, then warning, then good
    health_order = {"critical": 0, "warning": 1, "good": 2}
    result["_sort"] = result["Health"].map(health_order)
    result = result.sort_values(["_sort", "Inbound Links"]).drop(columns=["_sort"])
    result = result.reset_index(drop=True)

    return result
