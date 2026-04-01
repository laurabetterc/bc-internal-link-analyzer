"""Parser for the Priority URLs CSV."""

import pandas as pd
from src.config import PRIORITY_REQUIRED_COLUMNS


def parse_priority_urls_csv(uploaded_file) -> tuple[pd.DataFrame | None, str]:
    """Parse a Priority URLs CSV.

    Expected columns: URL, Target Keyword, and optionally Content Type.
    Returns (dataframe, error_message).
    """
    try:
        df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
    except Exception as e:
        return None, f"Could not read CSV file: {e}"

    df.columns = df.columns.str.strip()

    # Check required columns
    missing = [col for col in PRIORITY_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return None, (
            f"Missing required columns: {', '.join(missing)}. "
            f"Expected columns: URL, Target Keyword (and optionally Content Type)."
        )

    # Drop rows without a URL
    df = df.dropna(subset=["URL"])

    # Normalize — strip all whitespace variants (spaces, tabs, non-breaking spaces, newlines)
    df["URL"] = df["URL"].astype(str).str.replace(r'[\s\u00a0\u200b]+$', '', regex=True).str.replace(r'^[\s\u00a0\u200b]+', '', regex=True)
    df["Target Keyword"] = df["Target Keyword"].fillna("").str.strip()

    # Handle optional Content Type
    if "Content Type" in df.columns:
        df["Content Type"] = df["Content Type"].fillna("").str.strip()
    else:
        df["Content Type"] = ""

    has_content_type = (df["Content Type"] != "").sum()

    return df, ""
