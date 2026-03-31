"""Cocoon health analysis — compute intra-cocoon linking stats."""

import pandas as pd


def analyze_cocoon_health(
    cocoons: list[dict],
    cleaned_df: pd.DataFrame,
) -> pd.DataFrame:
    """Analyze internal linking health within each operator cocoon.

    For each cocoon, computes:
    - Number of pages
    - Existing intra-cocoon links (links between pages in the same cocoon)
    - Maximum possible intra-cocoon links (n * (n-1) for n pages)
    - Links pointing to the code page from sibling pages
    - Health score: good / weak / poor

    Args:
        cocoons: List of cocoon dicts from AI detection.
        cleaned_df: Cleaned link data.

    Returns:
        DataFrame with one row per cocoon.
    """
    if not cocoons:
        return pd.DataFrame()

    # Build a fast lookup of existing links
    existing_links = set(
        zip(cleaned_df["Source"].tolist(), cleaned_df["Destination"].tolist())
    )

    rows = []
    for cocoon in cocoons:
        operator = cocoon.get("operator", "Unknown")
        pages = set(cocoon.get("pages", []))
        code_page = cocoon.get("code_page")
        n_pages = len(pages)

        if n_pages < 2:
            continue

        # Count intra-cocoon links
        intra_links = 0
        code_page_inbound = 0
        for src in pages:
            for dst in pages:
                if src == dst:
                    continue
                if (src, dst) in existing_links:
                    intra_links += 1
                    if dst == code_page:
                        code_page_inbound += 1

        # Maximum possible intra-cocoon links
        max_possible = n_pages * (n_pages - 1)
        completeness = intra_links / max_possible if max_possible > 0 else 0

        # Expected code page inbound: every sibling should link to code page
        expected_code_inbound = n_pages - 1 if code_page else 0
        code_page_ratio = (
            code_page_inbound / expected_code_inbound
            if expected_code_inbound > 0
            else 0
        )

        # Health scoring
        # Good: >60% completeness AND code page gets >60% of expected links
        # Weak: >30% completeness OR code page gets some links
        # Poor: <30% completeness AND code page gets <30% of expected links
        if completeness >= 0.6 and code_page_ratio >= 0.6:
            health = "good"
        elif completeness >= 0.3 or code_page_ratio >= 0.3:
            health = "weak"
        else:
            health = "poor"

        rows.append({
            "Operator": operator,
            "Pages": n_pages,
            "Intra-links": intra_links,
            "Max Possible": max_possible,
            "Completeness": round(completeness * 100, 1),
            "Code Page Links": code_page_inbound,
            "Expected Code Links": expected_code_inbound,
            "Health": health,
            "code_page_url": code_page or "",
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        # Sort: poor first, then weak, then good
        health_order = {"poor": 0, "weak": 1, "good": 2}
        result["_sort"] = result["Health"].map(health_order)
        result = result.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return result
