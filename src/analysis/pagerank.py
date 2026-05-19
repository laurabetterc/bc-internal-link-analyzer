"""PageRank calculation using networkx.

Two flavours:
  - `compute_pagerank` (basic): every link counts the same.
  - `compute_weighted_pagerank` (v2): links are weighted by Link Position so
    a content link counts much more than a sidebar / footer / nav link.
"""

import pandas as pd
import networkx as nx

from src.config import PAGERANK_DAMPING, PAGERANK_MAX_ITER


# Empirical weights — content links are the strongest signal Google uses;
# sidebar/footer/nav are largely ignored or heavily discounted in modern
# ranking models (Gary Illyes / John Mueller commentary, plus internal
# experiments in BC's content team). Aside is treated as half-content.
LINK_POSITION_WEIGHTS: dict[str, float] = {
    "Content": 1.0,
    "Aside": 0.5,
    "Sidebar": 0.3,
    "Navigation": 0.2,
    "Header": 0.2,
    "Footer": 0.1,
}
DEFAULT_LINK_WEIGHT = 0.5  # unknown / empty Link Position


def compute_pagerank(df: pd.DataFrame) -> dict[str, float]:
    """Calculate basic PageRank for all pages in the link graph.

    Args:
        df: Cleaned DataFrame with Source and Destination columns.

    Returns:
        Dictionary mapping URL to PageRank score.
    """
    G = nx.DiGraph()

    for _, row in df.iterrows():
        G.add_edge(row["Source"], row["Destination"])

    scores = nx.pagerank(
        G,
        alpha=PAGERANK_DAMPING,
        max_iter=PAGERANK_MAX_ITER,
    )

    return scores


def _is_follow_link(value) -> bool:
    """Screaming Frog's Follow column can be 'True'/'False' (string) or bool.
    Treats missing/unknown as follow (the safe default — don't silently strip
    PR from links we can't classify)."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("false", "no", "0", "nofollow"):
        return False
    return True


def compute_weighted_pagerank(
    df: pd.DataFrame,
    external_link_counts: dict[str, int] | None = None,
) -> dict[str, float]:
    """PageRank weighted by Link Position (v2 — content > sidebar > nav > footer).

    Falls back to basic PR if `Link Position` isn't available. When multiple
    edges connect the same source → target (e.g., one content link + one
    footer link to the same page), their weights sum so the strongest edge
    wins without artificially deduplicating.

    `Follow` column (if present): nofollow links don't pass PR — their edge
    weight is set to 0. Treats missing/unknown values as follow (safe default).

    `external_link_counts`: optional dict of source URL → outbound external
    link count (links to other domains, filtered out before this point in the
    pipeline). When provided, internal edge weights from each source are
    diluted by the fraction of its links that point externally — a page
    losing PR to many external destinations passes proportionally less to
    each internal neighbour.
    """
    if "Link Position" not in df.columns:
        return compute_pagerank(df)

    weights = df["Link Position"].map(LINK_POSITION_WEIGHTS).fillna(DEFAULT_LINK_WEIGHT)

    if "Follow" in df.columns:
        follow_mask = df["Follow"].apply(_is_follow_link)
        # Nofollow → zero weight (no PR transfer). Keep the edge in the
        # graph so the source page still appears as a node.
        weights = weights.where(follow_mask, 0.0)

    edges_df = pd.DataFrame({
        "Source": df["Source"],
        "Destination": df["Destination"],
        "weight": weights,
    })
    # Sum per (source, target) so duplicate edges combine instead of overwrite.
    edges_df = edges_df.groupby(["Source", "Destination"], as_index=False)["weight"].sum()

    # External-link dilution: scale each source's outbound edge weights by
    # the proportion of its links that are internal. If a page links to 10
    # internal pages and 90 external ones, its internal edges carry only
    # 10/100 = 0.1 of their nominal weight.
    if external_link_counts:
        internal_counts = edges_df.groupby("Source")["weight"].count().to_dict()
        dilution: dict[str, float] = {}
        for src, internal_n in internal_counts.items():
            ext_n = external_link_counts.get(src, 0)
            total = internal_n + ext_n
            dilution[src] = internal_n / total if total > 0 else 1.0
        edges_df["weight"] = edges_df.apply(
            lambda r: r["weight"] * dilution.get(r["Source"], 1.0),
            axis=1,
        )

    G = nx.DiGraph()
    for _, row in edges_df.iterrows():
        G.add_edge(row["Source"], row["Destination"], weight=float(row["weight"]))

    scores = nx.pagerank(
        G,
        alpha=PAGERANK_DAMPING,
        max_iter=PAGERANK_MAX_ITER,
        weight="weight",
    )
    return scores


def compute_pagerank_comparison(scores_basic: dict[str, float], scores_weighted: dict[str, float]) -> pd.DataFrame:
    """Compare basic vs weighted PageRank — surface pages where placement matters most.

    Returns a DataFrame with columns: URL, Basic PR, Weighted PR, Δ Rank,
    sorted by absolute rank delta (biggest movers first). A negative Δ means
    the page ranks higher under weighted PR (gained from quality content links);
    positive Δ means it dropped (relied on nav/footer links).
    """
    if not scores_basic or not scores_weighted:
        return pd.DataFrame(columns=["URL", "Basic PR", "Weighted PR", "Basic Rank", "Weighted Rank", "Δ Rank"])

    basic_sorted = sorted(scores_basic.items(), key=lambda kv: kv[1], reverse=True)
    weighted_sorted = sorted(scores_weighted.items(), key=lambda kv: kv[1], reverse=True)
    basic_rank = {url: i + 1 for i, (url, _) in enumerate(basic_sorted)}
    weighted_rank = {url: i + 1 for i, (url, _) in enumerate(weighted_sorted)}

    rows = []
    for url in set(scores_basic) | set(scores_weighted):
        b_pr = scores_basic.get(url, 0.0)
        w_pr = scores_weighted.get(url, 0.0)
        b_r = basic_rank.get(url, len(basic_rank) + 1)
        w_r = weighted_rank.get(url, len(weighted_rank) + 1)
        rows.append({
            "URL": url,
            "Basic PR": b_pr,
            "Weighted PR": w_pr,
            "Basic Rank": b_r,
            "Weighted Rank": w_r,
            "Δ Rank": w_r - b_r,  # negative = improved under weighted
        })

    out = pd.DataFrame(rows)
    out["_abs_delta"] = out["Δ Rank"].abs()
    out = out.sort_values(["_abs_delta", "Weighted PR"], ascending=[False, False]).drop(columns=["_abs_delta"])
    return out.reset_index(drop=True)


def get_top_pages(scores: dict[str, float], n: int = 50) -> pd.DataFrame:
    """Get the top N pages by PageRank score.

    Returns:
        DataFrame with URL, PageRank, and Rank columns.
    """
    sorted_pages = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]

    df = pd.DataFrame(sorted_pages, columns=["URL", "PageRank"])
    df["Rank"] = range(1, len(df) + 1)
    df = df[["Rank", "URL", "PageRank"]]

    return df


def get_pagerank_distribution(scores: dict[str, float]) -> pd.DataFrame:
    """Get PageRank scores as a DataFrame for charting.

    Returns:
        DataFrame with URL and PageRank columns, sorted descending.
    """
    df = pd.DataFrame(list(scores.items()), columns=["URL", "PageRank"])
    df = df.sort_values("PageRank", ascending=False).reset_index(drop=True)
    return df
