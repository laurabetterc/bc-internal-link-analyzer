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
    removal_candidates: list[dict] | None = None,
    update_candidates: list[dict] | None = None,
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

    # Build (source, target) → candidate indexes for removal + update so
    # we can flag existing rows with the right status instead of emitting
    # parallel rows the team would have to cross-reference manually.
    # Removal supersedes update (a link being removed doesn't need a better
    # anchor) — already enforced upstream in `compute_update_candidates`.
    removal_index: dict[tuple[str, str], dict] = {}
    for cand in (removal_candidates or []):
        key = (cand.get("source_url", ""), cand.get("target_url", ""))
        if key[0] and key[1]:
            removal_index[key] = cand
    update_index: dict[tuple[str, str], dict] = {}
    for cand in (update_candidates or []):
        key = (cand.get("source_url", ""), cand.get("target_url", ""))
        if key[0] and key[1]:
            update_index[key] = cand

    # All existing links from cleaned data. Status defaults to "live"; flips
    # to "to remove" (highest priority) when in the removal index, or "to
    # update" when in the update index. Removal supersedes update.
    for _, link_row in cleaned_df.iterrows():
        target = link_row["Destination"]
        source = link_row["Source"]
        cand = removal_index.get((source, target))
        if cand:
            removal_type = cand.get("removal_type", "")
            tag = "[Hard-fail]" if removal_type == "hard_fail" else "[Swap candidate]"
            rows.append({
                "Source URL": source,
                "Target URL": target,
                "Anchor": link_row.get("Anchor", "") or cand.get("anchor", ""),
                "Status": "to remove",
                "Target Status": _target_status(target, None),
                "Section": _section_label(source),
                "Score": int(cand.get("relevance_score", 0)),
                "Priority": "review",
                "Reason": f"{tag} {cand.get('reason', '')}".strip(),
            })
            continue
        upd = update_index.get((source, target))
        if upd:
            # Surface the SUGGESTED anchor in the Anchor column (so the team
            # can copy it directly) and keep the original in the Reason.
            rows.append({
                "Source URL": source,
                "Target URL": target,
                "Anchor": upd.get("suggested_anchor", ""),
                "Status": "to update",
                "Target Status": _target_status(target, None),
                "Section": _section_label(source),
                "Score": "",
                "Priority": "review",
                "Reason": f"[Update anchor] {upd.get('reason', '')}".strip(),
            })
            continue
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

    # Sort: 301 candidates first (highest urgency), then "to remove" (action
    # needed), then "to update" (anchor change), then "to add" (new recs),
    # then "live" (informational).
    status_order = {"301 candidate": 0, "to remove": 1, "to update": 2, "to add": 3, "live": 4}
    df["_sort"] = df["Status"].map(status_order).fillna(99)
    df = df.sort_values(["_sort", "Target URL", "Source URL"]).drop(columns=["_sort"])

    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()
