"""CSV export — generate the linking plan as a CSV file."""

from io import StringIO

import pandas as pd


def generate_linking_plan_csv(
    cleaned_df: pd.DataFrame,
    recommendations: list[dict],
) -> str:
    """Generate the linking plan as a CSV string.

    Includes ALL links on the site (full perspective):
    - Existing links with status "live"
    - AI recommended links with status "to add"

    Columns: Source URL, Target URL, Anchor, Status, Priority, Reason

    Returns:
        CSV content as a string (ready for st.download_button).
    """
    rows = []

    # All existing links from cleaned data (status: "live")
    for _, link_row in cleaned_df.iterrows():
        rows.append({
            "Source URL": link_row["Source"],
            "Target URL": link_row["Destination"],
            "Anchor": link_row.get("Anchor", ""),
            "Status": "live",
            "Priority": "",
            "Reason": "",
        })

    # AI recommendations (status: "to add")
    for rec in recommendations:
        rows.append({
            "Source URL": rec.get("source_url", ""),
            "Target URL": rec.get("target_url", ""),
            "Anchor": rec.get("suggested_anchor", ""),
            "Status": "to add",
            "Priority": rec.get("priority", ""),
            "Reason": rec.get("reason", ""),
        })

    df = pd.DataFrame(rows, columns=["Source URL", "Target URL", "Anchor", "Status", "Priority", "Reason"])

    # Sort: "to add" first (actionable), then "live"
    status_order = {"to add": 0, "live": 1}
    df["_sort"] = df["Status"].map(status_order)
    df = df.sort_values(["_sort", "Target URL", "Source URL"]).drop(columns=["_sort"])

    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()
