"""Parser for Screaming Frog 'All Inlinks' CSV export."""

from collections import Counter
from urllib.parse import urlparse

import pandas as pd
from src.config import SF_REQUIRED_COLUMNS


def validate_columns(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """Check that all required columns are present.
    Returns (is_valid, missing_columns).
    """
    missing = [col for col in SF_REQUIRED_COLUMNS if col not in df.columns]
    return len(missing) == 0, missing


def _get_domain(url: str) -> str:
    """Extract the registrable domain from a URL (e.g., 'bolavip.com' from 'https://www.bolavip.com/mx/...')."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    # Strip www. prefix
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


def _filter_external_links(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove links where Source or Destination is on a different domain.

    Detects the primary domain automatically (most common domain in Source column).
    Returns (filtered_df, removed_count).
    """
    # Find the primary domain from Source URLs (most frequent)
    source_domains = df["Source"].apply(_get_domain)
    domain_counts = Counter(source_domains)
    if not domain_counts:
        return df, 0

    primary_domain = domain_counts.most_common(1)[0][0]
    if not primary_domain:
        return df, 0

    # Keep only rows where both Source and Destination are on the primary domain
    dest_domains = df["Destination"].apply(_get_domain)
    mask = (source_domains == primary_domain) & (dest_domains == primary_domain)
    removed = int((~mask).sum())

    return df[mask].copy(), removed


def parse_screaming_frog_csv(uploaded_file) -> tuple[pd.DataFrame | None, str]:
    """Parse a Screaming Frog All Inlinks CSV.

    Returns (dataframe, error_message).
    If successful, error_message is empty.
    """
    try:
        df = pd.read_csv(uploaded_file, encoding="utf-8-sig", low_memory=False)
    except Exception as e:
        return None, f"Could not read CSV file: {e}"

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    is_valid, missing = validate_columns(df)
    if not is_valid:
        return None, (
            f"Missing required columns: {', '.join(missing)}. "
            f"Make sure you're uploading the 'All Inlinks' export from Screaming Frog."
        )

    # Keep only Hyperlink rows (ignore images, CSS, JS, etc.)
    if "Type" in df.columns:
        df = df[df["Type"] == "Hyperlink"].copy()

    # Drop rows where Source or Destination is missing
    df = df.dropna(subset=["Source", "Destination"])

    # Normalize URLs: strip whitespace
    df["Source"] = df["Source"].str.strip()
    df["Destination"] = df["Destination"].str.strip()

    # Remove external links (different domain than the primary site)
    df, _removed = _filter_external_links(df)

    # Fill empty anchors with empty string
    df["Anchor"] = df["Anchor"].fillna("")

    return df, ""
