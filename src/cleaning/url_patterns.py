"""Step 2: Detect and filter URL patterns."""

import re
from urllib.parse import urlparse, parse_qs
from collections import Counter

import pandas as pd


# ---- Pagination detection ----

# Query param names commonly used for pagination
_PAGINATION_PARAMS = {"page", "p", "paged", "pg", "pagina", "offset", "start"}

# Path patterns like /page/2, /pagina/3 (at the end of the path)
_PAGINATION_PATH_RE = re.compile(r"/(?:page|p|pagina|paged)/\d+/?$", re.IGNORECASE)

# Short numeric ending like /category/1, /tags/15 (last segment is a number under 100)
_NUMERIC_ENDING_RE = re.compile(r"/(\d{1,2})/?$")


def detect_pagination_urls(df: pd.DataFrame) -> dict:
    """Detect paginated URLs from Source and Destination columns.

    Catches two types of pagination:
    - Query parameters: ?page=2, ?p=3, ?paged=1, ?pagina=5, ?offset=20, ?start=10
    - Path segments: /page/2, /pagina/3, /p/4

    Returns dict with:
        urls: set of paginated URLs
        count: number of unique paginated URLs
        link_count: number of links involving paginated URLs
        examples: up to 5 example URLs
        patterns_found: list of detected pagination types (e.g., "?page=N", "/page/N")
    """
    all_urls = pd.concat([df["Source"], df["Destination"]]).unique()

    paginated = set()
    patterns_found = set()

    for url in all_urls:
        try:
            parsed = urlparse(url)
        except Exception:
            continue

        # Check query parameters (e.g., ?page=2, ?p=3)
        if parsed.query:
            params = parse_qs(parsed.query)
            for param_name in _PAGINATION_PARAMS:
                if param_name in params:
                    values = params[param_name]
                    if any(v.isdigit() for v in values):
                        paginated.add(url)
                        patterns_found.add(f"?{param_name}=N")
                        break

        # Check path patterns (e.g., /page/2, /pagina/3)
        if _PAGINATION_PATH_RE.search(parsed.path):
            paginated.add(url)
            match = _PAGINATION_PATH_RE.search(parsed.path)
            if match:
                # Extract the keyword (e.g., "page" from "/page/2")
                segment = match.group().strip("/").split("/")[0]
                patterns_found.add(f"/{segment}/N")
        # Check short numeric endings (e.g., /category/1, /tags/15)
        elif _NUMERIC_ENDING_RE.search(parsed.path):
            num_match = _NUMERIC_ENDING_RE.search(parsed.path)
            num = int(num_match.group(1))
            if num < 100:
                paginated.add(url)
                patterns_found.add("/…/N (numeric ending)")

    # Count how many links involve paginated URLs
    link_count = 0
    if paginated:
        mask = df["Source"].isin(paginated) | df["Destination"].isin(paginated)
        link_count = int(mask.sum())

    examples = sorted(paginated)[:5]

    return {
        "urls": paginated,
        "count": len(paginated),
        "link_count": link_count,
        "examples": examples,
        "patterns_found": sorted(patterns_found),
    }


def filter_pagination(df: pd.DataFrame, pagination_urls: set) -> pd.DataFrame:
    """Remove links where Source or Destination is a paginated URL."""
    if not pagination_urls:
        return df.copy()
    mask = df["Source"].isin(pagination_urls) | df["Destination"].isin(pagination_urls)
    return df[~mask].copy()


# ---- Template link detection (false "Content" links) ----


def detect_template_links(df: pd.DataFrame, min_page_ratio: float = 0.5, min_pages: int = 50) -> dict:
    """Detect links labeled 'Content' that are actually sitewide template elements.

    Sites with non-semantic HTML (e.g. <div> instead of <nav>) cause Screaming Frog
    to misclassify navigation bars, sticky menus, or sidebar widgets as 'Content' links.
    Detection: same Link Path (XPath) appearing on a high percentage of source pages.
    """
    if "Link Path" not in df.columns or "Link Position" not in df.columns:
        return {"paths": [], "total_links": 0, "total_paths": 0}

    content_links = df[df["Link Position"] == "Content"].copy()
    if content_links.empty:
        return {"paths": [], "total_links": 0, "total_paths": 0}

    content_links = content_links.dropna(subset=["Link Path"])
    if content_links.empty:
        return {"paths": [], "total_links": 0, "total_paths": 0}

    total_source_pages = df["Source"].nunique()
    threshold = max(min_pages, int(total_source_pages * min_page_ratio))

    path_pages = content_links.groupby("Link Path")["Source"].nunique()
    template_paths = path_pages[path_pages >= threshold]

    if template_paths.empty:
        return {"paths": [], "total_links": 0, "total_paths": 0}

    paths_info = []
    total_links = 0
    for path, page_count in template_paths.items():
        path_data = content_links[content_links["Link Path"] == path]
        anchors = path_data["Anchor"].value_counts().head(3).index.tolist()
        destinations = path_data["Destination"].value_counts().head(2).index.tolist()
        link_count = len(path_data)
        total_links += link_count
        paths_info.append({
            "path": path,
            "anchors": anchors,
            "destinations": destinations,
            "page_count": int(page_count),
            "page_ratio": page_count / total_source_pages,
            "link_count": link_count,
        })

    paths_info.sort(key=lambda x: x["page_count"], reverse=True)
    return {"paths": paths_info, "total_links": total_links, "total_paths": len(paths_info)}


def filter_template_links(df: pd.DataFrame, template_paths: list[str]) -> pd.DataFrame:
    """Remove links whose Link Path matches any of the given template paths."""
    if not template_paths or "Link Path" not in df.columns:
        return df.copy()
    path_set = set(template_paths)
    return df[~df["Link Path"].isin(path_set)].copy()


def extract_path_prefix(url: str, depth: int = 2) -> str:
    """Extract path prefix up to a given depth.

    Example: 'https://site.com/mx/apuestas/codigos/code-1xbet' with depth=3
    returns '/mx/apuestas/codigos/*'
    """
    try:
        path = urlparse(url).path.rstrip("/")
    except Exception:
        return ""

    parts = path.split("/")
    # parts[0] is '' (before the first /)
    if len(parts) <= depth + 1:
        return ""

    prefix = "/".join(parts[: depth + 1]) + "/*"
    return prefix


def detect_url_patterns(df: pd.DataFrame, min_urls: int = 5) -> pd.DataFrame:
    """Detect recurring URL patterns from Source and Destination URLs.

    Scans at multiple path depths to find the most meaningful groupings.
    Shows the most specific patterns that have enough URLs to be interesting.
    Returns a DataFrame with columns: Pattern, Example, Count, Keep (default True).
    """
    all_urls = pd.concat([df["Source"], df["Destination"]]).unique()

    # Collect patterns at each depth
    depth_patterns = {}  # depth -> {pattern: set of urls}
    for depth in [1, 2, 3, 4]:
        depth_patterns[depth] = {}
        for url in all_urls:
            prefix = extract_path_prefix(url, depth)
            if prefix:
                if prefix not in depth_patterns[depth]:
                    depth_patterns[depth][prefix] = set()
                depth_patterns[depth][prefix].add(url)

    # Strategy: prefer the most specific (deepest) pattern that has >= min_urls.
    # If a deeper pattern captures most URLs of a shallower pattern, show the deeper one.
    # If a shallower pattern has many URLs NOT covered by deeper patterns, show it too.
    final_patterns = {}  # pattern -> set of urls
    covered_urls = set()

    # Start from deepest to shallowest
    for depth in [4, 3, 2, 1]:
        for pattern, urls in sorted(
            depth_patterns[depth].items(), key=lambda x: len(x[1]), reverse=True
        ):
            if len(urls) < min_urls:
                continue

            # Count how many URLs are NOT yet covered by a more specific pattern
            new_urls = urls - covered_urls
            if len(new_urls) >= min_urls:
                final_patterns[pattern] = urls
                covered_urls.update(urls)

    # Count links (not just URLs) for each pattern
    all_links_source = df["Source"].tolist()
    all_links_dest = df["Destination"].tolist()

    pattern_examples = {}
    pattern_link_counts = {}

    for pattern in final_patterns:
        prefix = pattern.rstrip("*").rstrip("/")
        urls_in_pattern = final_patterns[pattern]
        # Pick a real example URL
        for u in urls_in_pattern:
            try:
                pattern_examples[pattern] = urlparse(u).path
                break
            except Exception:
                pass

        # Count links involving these URLs
        link_count = 0
        for src, dst in zip(all_links_source, all_links_dest):
            try:
                src_path = urlparse(src).path.rstrip("/")
                dst_path = urlparse(dst).path.rstrip("/")
            except Exception:
                continue
            if src_path.startswith(prefix) or dst_path.startswith(prefix):
                link_count += 1
        pattern_link_counts[pattern] = link_count

    # Remove patterns that are too broad (cover >80% of all URLs)
    total_urls = len(all_urls)
    too_broad = [p for p, urls in final_patterns.items() if len(urls) / total_urls > 0.8]
    for p in too_broad:
        del final_patterns[p]

    # Build result
    rows = []
    for pattern in sorted(final_patterns.keys()):
        rows.append({
            "Pattern": pattern,
            "Example": pattern_examples.get(pattern, ""),
            "URLs": len(final_patterns[pattern]),
            "Links": pattern_link_counts.get(pattern, 0),
            "Exclude": False,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("Links", ascending=False).reset_index(drop=True)

    # Auto-suggest excluding common non-content patterns
    exclude_hints = [
        "autor", "author", "page/", "tag/", "category", "feed",
        "wp-", "staff", "goto/", "redirect", "print",
    ]
    if not result.empty:
        for idx, row in result.iterrows():
            pattern_lower = row["Pattern"].lower()
            if any(hint in pattern_lower for hint in exclude_hints):
                result.at[idx, "Exclude"] = True

    return result


def is_substring_pattern(pattern: str) -> bool:
    """Check if a pattern is a substring match (not a path prefix).

    Substring patterns don't start with '/' — e.g. '-x-', 'old-page'.
    Path prefix patterns start with '/' — e.g. '/mx/autor/*'.
    """
    return not pattern.startswith("/")


def filter_by_patterns(df: pd.DataFrame, exclude_patterns: list[str]) -> pd.DataFrame:
    """Remove links where Source or Destination matches any excluded pattern.

    Supports two types of patterns:
    - Path prefix (starts with /): e.g. '/mx/autor/*' matches URL paths starting with /mx/autor
    - Substring (doesn't start with /): e.g. '-x-' matches any URL containing '-x-'
    """
    if not exclude_patterns:
        return df.copy()

    prefixes = [p.rstrip("*").rstrip("/") for p in exclude_patterns if not is_substring_pattern(p)]
    substrings = [p for p in exclude_patterns if is_substring_pattern(p)]

    def url_matches_any(url: str) -> bool:
        try:
            path = urlparse(url).path.rstrip("/")
        except Exception:
            return False
        if any(path.startswith(prefix) for prefix in prefixes):
            return True
        if any(sub in url for sub in substrings):
            return True
        return False

    mask = df["Source"].apply(url_matches_any) | df["Destination"].apply(url_matches_any)
    return df[~mask].copy()
