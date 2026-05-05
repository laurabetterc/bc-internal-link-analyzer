"""CSV export — generate the linking plan as a CSV file."""

from io import StringIO

import pandas as pd

from src.cleaning.language import extract_lang_segment


def _section_label(url: str) -> str:
    """Render a section code for a URL ('/it/', '/mx/', '(root)' for no prefix)."""
    code = extract_lang_segment(url or "")
    return f"/{code}/" if code else "(root)"


def generate_linking_plan_csv(
    cleaned_df: pd.DataFrame,
    recommendations: list[dict],
    orphan_urls: set[str] | None = None,
    priority_urls: set[str] | None = None,
    redirect_candidates: list[dict] | None = None,
) -> str:
    """Generate the linking plan as a CSV string.

    Includes ALL links on the site (full perspective):
    - Existing links with status "live"
    - AI recommended links with status "to add"

    Columns: Source URL, Target URL, Anchor, Status, Target Status, Section,
    Score, Priority, Reason. The Section column shows the URL section
    (language / country prefix). After Phase A's intra-section filter and
    Phase B6's cross-section block, source and target always share a section
    — so one column is enough.
    """
    orphans = orphan_urls or set()
    priorities = priority_urls or set()

    def _target_status(target_url: str, rec: dict | None = None) -> str:
        if rec and rec.get("is_coverage_fallback"):
            return "Coverage"
        if rec and rec.get("is_fallback"):
            return "Fallback"
        if target_url in orphans:
            return "Orphan"
        if target_url in priorities:
            return "Priority"
        return "Standard"

    def _tagged_reason(rec: dict, status: str) -> str:
        base = rec.get("reason", "")
        # Preserve any pre-existing tag (orphan_guarantee, coverage_guarantee, etc.)
        if (base.startswith("[Orphan target]") or base.startswith("[Priority target]")
                or base.startswith("[Fallback link]") or base.startswith("[Coverage fallback]")):
            return base
        if status == "Orphan":
            return f"[Orphan target] {base}".strip()
        if status == "Priority":
            return f"[Priority target] {base}".strip()
        if status == "Fallback":
            return f"[Fallback link] {base}".strip()
        if status == "Coverage":
            return f"[Coverage fallback] {base}".strip()
        return base

    rows = []

    # All existing links from cleaned data (status: "live")
    for _, link_row in cleaned_df.iterrows():
        target = link_row["Destination"]
        source = link_row["Source"]
        rows.append({
            "Source URL": source,
            "Target URL": target,
            "Anchor": link_row.get("Anchor", ""),
            "Status": "live",
            "Target Status": _target_status(target, None),
            "Section": _section_label(source),
            "Score": "",
            "Priority": "",
            "Reason": "",
        })

    # AI recommendations (status: "to add"). Coverage fallbacks share the
    # same Status value — the [Coverage fallback] tag in the Reason column
    # is the filter signal, the Status column stays simple for the team.
    for rec in recommendations:
        target = rec.get("target_url", "")
        source = rec.get("source_url", "")
        target_status_val = _target_status(target, rec)
        rows.append({
            "Source URL": source,
            "Target URL": target,
            "Anchor": rec.get("suggested_anchor", ""),
            "Status": "to add",
            "Target Status": target_status_val,
            "Section": _section_label(source),
            "Score": int(rec.get("relevance_score", 0)),
            "Priority": rec.get("priority", ""),
            "Reason": _tagged_reason(rec, target_status_val),
        })

    # C3 — recurring-event 301 redirect candidates
    for cand in (redirect_candidates or []):
        past = cand.get("past_url", "")
        current = cand.get("current_url", "")
        rows.append({
            "Source URL": past,
            "Target URL": current,
            "Anchor": "",
            "Status": "301 candidate",
            "Target Status": "Redirect",
            "Section": _section_label(past),
            "Score": "",
            "Priority": "",
            "Reason": (
                f"Past edition of recurring series "
                f"'{cand.get('series', '')}' ({cand.get('past_year', '')}) — "
                f"301-redirect to current edition ({cand.get('current_year', '')})."
            ),
        })

    df = pd.DataFrame(
        rows,
        columns=["Source URL", "Target URL", "Anchor", "Status", "Target Status", "Section", "Score", "Priority", "Reason"],
    )

    # Sort: 301 candidates first (highest urgency), then "to add", then "live".
    status_order = {"301 candidate": 0, "to add": 1, "live": 2}
    df["_sort"] = df["Status"].map(status_order).fillna(99)
    df = df.sort_values(["_sort", "Target URL", "Source URL"]).drop(columns=["_sort"])

    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()
