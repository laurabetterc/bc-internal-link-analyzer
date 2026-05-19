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


def get_primary_domain(df: pd.DataFrame) -> str:
    """Extract the primary domain from the Source column (most frequent domain)."""
    source_domains = df["Source"].apply(_get_domain)
    domain_counts = Counter(source_domains)
    if not domain_counts:
        return "unknown-site"
    primary = domain_counts.most_common(1)[0][0]
    return primary or "unknown-site"


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
    # Supports multiple Screaming Frog languages: English ("Hyperlink"), French ("Hyperlien"), etc.
    if "Type" in df.columns:
        hyperlink_variants = {"Hyperlink", "Hyperlien", "Hiperenlace", "Hyperlink-Tag", "Collegamento ipertestuale"}
        df = df[df["Type"].isin(hyperlink_variants)].copy()

    # Normalize Link Position to canonical English values — Screaming Frog localizes this column.
    if "Link Position" in df.columns:
        position_variants = {
            # Content
            "Contenu": "Content", "Contenido": "Content", "Inhalt": "Content", "Contenuto": "Content",
            # Navigation
            "Navigation": "Navigation", "Navegación": "Navigation", "Navigazione": "Navigation",
            # Header
            "En-tête": "Header", "Entête": "Header", "Cabecera": "Header", "Encabezado": "Header", "Kopfzeile": "Header", "Intestazione": "Header",
            # Footer
            "Pied de page": "Footer", "Pie de página": "Footer", "Fußzeile": "Footer", "Piè di pagina": "Footer",
            # Sidebar / Aside
            "Barre latérale": "Sidebar", "Barra lateral": "Sidebar", "Seitenleiste": "Sidebar", "Barra laterale": "Sidebar",
            "Aparté": "Aside",
        }
        df["Link Position"] = df["Link Position"].replace(position_variants)

    # Drop rows where Source or Destination is missing
    df = df.dropna(subset=["Source", "Destination"])

    # Normalize URLs: strip whitespace (including non-breaking spaces)
    df["Source"] = df["Source"].str.replace('\u00a0', ' ', regex=False).str.replace('\u200b', '', regex=False).str.strip()
    df["Destination"] = df["Destination"].str.replace('\u00a0', ' ', regex=False).str.replace('\u200b', '', regex=False).str.strip()

    # Capture external-link counts per source BEFORE filtering them out, so
    # PageRank v2 can dilute internal edge weights accordingly. A page linking
    # to many external destinations passes proportionally less PR internally.
    src_domains_pre = df["Source"].apply(_get_domain)
    dest_domains_pre = df["Destination"].apply(_get_domain)
    domain_counts = Counter(src_domains_pre)
    primary_domain = domain_counts.most_common(1)[0][0] if domain_counts else None
    external_link_counts: dict[str, int] = {}
    if primary_domain:
        external_mask = (src_domains_pre == primary_domain) & (dest_domains_pre != primary_domain)
        external_link_counts = (
            df.loc[external_mask, "Source"].value_counts().to_dict()
        )

    # Remove external links (different domain than the primary site)
    df, _removed = _filter_external_links(df)

    # Fill empty anchors with empty string
    df["Anchor"] = df["Anchor"].fillna("")

    # Filter broken / redirected destinations (3xx, 4xx, 5xx).
    # SEO rule: never recommend new links to broken or redirecting URLs, and
    # surface existing links pointing to them as `to remove` candidates so the
    # team can fix them. Broken sources are also dropped \u2014 a 404 page can't
    # host editorial fixes, and SF sometimes parses outbound links from
    # soft-404 bodies that shouldn't be treated as real linking signal.
    df, broken_links = _filter_broken_status(df)

    # Stash on the DataFrame so downstream consumers (removal_candidates,
    # dashboard panel) can use them without changing function signatures.
    df.attrs["external_link_counts"] = external_link_counts
    df.attrs["broken_links"] = broken_links

    return df, ""


def _filter_broken_status(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Drop rows whose destination or source has a 3xx/4xx/5xx status code.

    Returns (filtered_df, broken_edges). `broken_edges` is a list of dicts
    {source_url, target_url, status_code, anchor} for every dropped row where
    the destination was broken \u2014 these feed into removal_candidates so each
    becomes a `to remove` row for the team to act on. Edges dropped because
    the SOURCE is broken are not surfaced (the source page is gone \u2014 no
    actionable fix on our side).
    """
    if "Status Code" not in df.columns:
        return df, []

    # Status codes from pandas csv read are usually strings ("200", "404").
    # Coerce to string and take the first digit to bucket by class.
    codes = df["Status Code"].astype(str).str.strip()
    is_broken_dest = codes.str.match(r"^[3-5]\d\d$", na=False)

    # Detect sources that have ANY broken row tied to them. We treat the
    # source as broken if its own crawl-row (where the SF crawler hit it
    # directly) returned non-200. Simpler proxy: if the URL ever shows up
    # as a Destination with a non-200 code, it's broken regardless of where
    # else it appears.
    broken_url_set = set(df.loc[is_broken_dest, "Destination"].dropna().tolist())
    is_broken_src = df["Source"].isin(broken_url_set)

    # Build broken-edges list (destination side only, per the spec).
    # Iterate via zip on columns rather than itertuples — "Status Code" has
    # a space and gets renamed in itertuples namedtuples.
    broken_rows = df[is_broken_dest]
    broken_edges: list[dict] = [
        {
            "source_url": src,
            "target_url": dst,
            "status_code": str(code).strip(),
            "anchor": anchor or "",
        }
        for src, dst, code, anchor in zip(
            broken_rows["Source"],
            broken_rows["Destination"],
            broken_rows["Status Code"],
            broken_rows["Anchor"],
        )
    ]

    # Drop any row where destination or source is broken
    keep_mask = ~(is_broken_dest | is_broken_src)
    return df[keep_mask].copy(), broken_edges
