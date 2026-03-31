"""PageRank calculation using networkx."""

import pandas as pd
import networkx as nx

from src.config import PAGERANK_DAMPING, PAGERANK_MAX_ITER


def compute_pagerank(df: pd.DataFrame) -> dict[str, float]:
    """Calculate PageRank for all pages in the link graph.

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
