"""Step 1: Filter links by Link Position."""

import pandas as pd
from src.config import DEFAULT_KEEP_POSITIONS


def get_position_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Get a summary of link counts by Link Position.

    Returns a DataFrame with columns: Position, Count, Action.
    Sorted by count descending.
    """
    counts = (
        df["Link Position"]
        .fillna("Unknown")
        .value_counts()
        .reset_index()
    )
    counts.columns = ["Position", "Count"]

    # Mark default action
    counts["Action"] = counts["Position"].apply(
        lambda p: "Keep" if p in DEFAULT_KEEP_POSITIONS else "Remove"
    )

    return counts


def filter_by_positions(df: pd.DataFrame, keep_positions: list[str]) -> pd.DataFrame:
    """Filter the dataframe to only keep rows with the specified Link Positions."""
    return df[df["Link Position"].isin(keep_positions)].copy()
