"""CSV export — generate the linking plan as a CSV file."""

from io import StringIO

import pandas as pd


def generate_linking_plan_csv(
    cleaned_df: pd.DataFrame,
    recommendations: list[dict],
    orphan_urls: set[str] | None = None,
    priority_urls: set[str] | None = None,
) -> str:
    """Generate the linking plan as a CSV string.

    Includes ALL links on the site (full perspective):
    - Existing links with status "live"
    - AI recommended links with status "to add"

    Columns: Source URL, Target URL, Anchor, Status, Target Status, Score, Priority, Reason
    """
    orphans = orphan_urls or set()
    priorities = priority_urls or set()

    def _target_status(target_url: str, is_fallback: bool) -> str:
        if is_fallback:
            return "Fallback"
        if target_url in orphans:
            return "Orphan"
        if target_url in priorities:
            return "Priority"
        return "Standard"

    def _tagged_reason(rec: dict, status: str) -> str:
        base = rec.get("reason", "")
        if base.startswith("[Orphan target]") or base.startswith("[Priority target]") or base.startswith("[Fallback link]"):
            return base
        if status == "Orphan":
            return f"[Orphan target] {base}".strip()
        if status == "Priority":
            return f"[Priority target] {base}".strip()
        if status == "Fallback":
            return f"[Fallback link] {base}".strip()
        return base

    rows = []

    # All existing links from cleaned data (status: "live")
    for _, link_row in cleaned_df.iterrows():
        target = link_row["Destination"]
        rows.append({
            "Source URL": link_row["Source"],
            "Target URL": target,
            "Anchor": link_row.get("Anchor", ""),
            "Status": "live",
            "Target Status": _target_status(target, False),
            "Score": "",
            "Priority": "",
            "Reason": "",
        })

    # AI recommendations (status: "to add")
    for rec in recommendations:
        target = rec.get("target_url", "")
        target_status_val = _target_status(target, bool(rec.get("is_fallback")))
        rows.append({
            "Source URL": rec.get("source_url", ""),
            "Target URL": target,
            "Anchor": rec.get("suggested_anchor", ""),
            "Status": "to add",
            "Target Status": target_status_val,
            "Score": int(rec.get("relevance_score", 0)),
            "Priority": rec.get("priority", ""),
            "Reason": _tagged_reason(rec, target_status_val),
        })

    df = pd.DataFrame(
        rows,
        columns=["Source URL", "Target URL", "Anchor", "Status", "Target Status", "Score", "Priority", "Reason"],
    )

    # Sort: "to add" first (actionable), then "live"
    status_order = {"to add": 0, "live": 1}
    df["_sort"] = df["Status"].map(status_order)
    df = df.sort_values(["_sort", "Target URL", "Source URL"]).drop(columns=["_sort"])

    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()
