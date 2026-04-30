"""HTML report generator — self-contained, shareable analysis report.

Produces a standalone HTML file matching the Nordic Precision theme,
including all analysis results, charts, and tables.
"""

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.io as pio


def _health_dot(status: str) -> str:
    colors = {"critical": "#F87171", "warning": "#FBBF24", "good": "#34D399",
              "poor": "#F87171", "weak": "#FBBF24"}
    color = colors.get(status, "#94A3B8")
    return f'<span style="color:{color};">●</span>'


def _stat_card_html(value: str, label: str, danger: bool = False, accent: bool = False) -> str:
    color = "#F87171" if danger else ("#34D399" if accent else "#F0F4F8")
    return (
        f'<div style="background:rgba(15,29,43,0.7);border:1px solid rgba(37,64,85,0.6);'
        f'border-radius:12px;padding:20px 16px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:{color};font-family:Outfit,sans-serif;">{value}</div>'
        f'<div style="font-size:13px;color:#94A3B8;margin-top:4px;">{label}</div>'
        f'</div>'
    )


def _table_html(headers: list[str], rows: list[list[str]], max_height: str = "500px") -> str:
    """Build an HTML table with the Nordic theme."""
    ths = "".join(
        f'<th style="text-align:left;padding:10px 12px;border-bottom:1px solid rgba(37,64,85,0.6);'
        f'color:#94A3B8;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;'
        f'position:sticky;top:0;background:#0F1D2B;">{h}</th>'
        for h in headers
    )
    trs = ""
    for row in rows:
        tds = "".join(
            f'<td style="padding:8px 12px;border-bottom:1px solid rgba(37,64,85,0.3);'
            f'color:#F0F4F8;font-size:13px;max-width:400px;overflow:hidden;text-overflow:ellipsis;'
            f'white-space:nowrap;" title="{cell}">{cell}</td>'
            for cell in row
        )
        trs += f"<tr>{tds}</tr>\n"

    return (
        f'<div style="overflow:auto;max-height:{max_height};border:1px solid rgba(37,64,85,0.6);border-radius:8px;">'
        f'<table style="width:100%;border-collapse:collapse;"><thead><tr>{ths}</tr></thead>'
        f'<tbody>{trs}</tbody></table></div>'
    )


def generate_html_report(
    site_domain: str,
    audit: dict,
    pagerank_scores: dict[str, float],
    priority_health_df: pd.DataFrame,
    cocoon_health_df: pd.DataFrame | None,
    recommendations: list[dict],
    token_usage: dict | None,
    redirect_candidates: list[dict] | None = None,
) -> str:
    """Generate a self-contained HTML report with all analysis results.

    Returns the HTML content as a string.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # --- PageRank chart (Plotly to HTML) ---
    pr_values = sorted(pagerank_scores.values())
    pr_df = pd.DataFrame({"PageRank": pr_values})
    fig = px.histogram(
        pr_df, x="PageRank", nbins=50,
        color_discrete_sequence=["#0EA5E9"],
        labels={"PageRank": "PageRank Score", "count": "Number of Pages"},
    )
    fig.update_layout(
        xaxis_title="PageRank Score",
        yaxis_title="Number of Pages",
        bargap=0.05,
        plot_bgcolor="#0B1621",
        paper_bgcolor="#0B1621",
        font=dict(family="DM Sans, sans-serif", size=13, color="#94A3B8"),
        margin=dict(t=10, b=40, l=50, r=20),
        height=350,
    )
    fig.update_xaxes(gridcolor="rgba(37, 64, 85, 0.4)", zerolinecolor="rgba(37, 64, 85, 0.4)")
    fig.update_yaxes(gridcolor="rgba(37, 64, 85, 0.4)", zerolinecolor="rgba(37, 64, 85, 0.4)")
    plotly_chart_html = pio.to_html(fig, full_html=False, include_plotlyjs="cdn")

    # --- Top pages by PageRank ---
    sorted_pages = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:30]
    top_pages_rows = [
        [str(i + 1), url, f"{score:.6f}"]
        for i, (url, score) in enumerate(sorted_pages)
    ]

    # --- Priority URLs health ---
    health_icons = {"critical": "🔴", "warning": "🟡", "good": "🟢"}
    priority_rows = []
    for _, row in priority_health_df.iterrows():
        priority_rows.append([
            health_icons.get(row["Health"], ""),
            str(row["URL"]),
            str(row["Target Keyword"]),
            str(row.get("Content Type", "")),
            str(row["Inbound Links"]),
            f"{row['PageRank']:.6f}" if "PageRank" in row and pd.notna(row["PageRank"]) else "—",
        ])

    n_critical = (priority_health_df["Health"] == "critical").sum()
    n_warning = (priority_health_df["Health"] == "warning").sum()
    n_good = (priority_health_df["Health"] == "good").sum()

    # --- Cocoon health ---
    cocoon_section = ""
    if cocoon_health_df is not None and not cocoon_health_df.empty:
        cocoon_icons = {"poor": "🔴", "weak": "🟡", "good": "🟢"}
        n_poor = (cocoon_health_df["Health"] == "poor").sum()
        n_weak = (cocoon_health_df["Health"] == "weak").sum()
        n_cgood = (cocoon_health_df["Health"] == "good").sum()

        cocoon_rows = []
        for _, row in cocoon_health_df.iterrows():
            cocoon_rows.append([
                cocoon_icons.get(row["Health"], ""),
                str(row["Operator"]),
                str(row["Pages"]),
                f"{row['Intra-links']} / {row['Max Possible']}",
                f"{row['Completeness']:.1f}%",
                f"{row['Code Page Links']} →",
                str(row["Health"]),
            ])

        cocoon_section = f"""
        <h2 style="margin-top:48px;">Cocoon Health <span style="background:linear-gradient(135deg,#005947,#00A868);
            padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;vertical-align:middle;">AI</span></h2>
        <p style="color:#94A3B8;font-size:14px;margin-bottom:16px;">
            Operator-based silos detected by AI. Each cocoon groups pages about the same operator.</p>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">
            {_stat_card_html(str(n_poor), "Poor", danger=True)}
            {_stat_card_html(str(n_weak), "Weak")}
            {_stat_card_html(str(n_cgood), "Good", accent=True)}
        </div>
        {_table_html(["", "Operator", "Pages", "Intra-links", "Completeness", "Code Page Links", "Health"], cocoon_rows)}
        """

    # --- Orphan URL list (Laura request — full URL list in the report) ---
    orphan_section = ""
    all_orphan_pages = audit.get("all_orphan_pages") or [
        {"url": u, "in_crawl": True} for u in audit.get("orphan_pages", [])
    ]
    if all_orphan_pages:
        orphan_rows = [
            [r["url"], "In crawl" if r["in_crawl"] else "Not in crawl"]
            for r in all_orphan_pages
        ]
        not_in_crawl = sum(1 for r in all_orphan_pages if not r["in_crawl"])
        copy_text = "\\n".join(r["url"] for r in all_orphan_pages).replace("'", "\\'")
        note = (
            f"{not_in_crawl:,} of them aren't in the crawl at all — these are the most critical."
            if not_in_crawl > 0 else ""
        )
        orphan_section = f"""
        <h2 style="margin-top:48px;">Orphan Pages ({len(all_orphan_pages)})</h2>
        <p class="section-desc">
            Pages with zero inbound internal links. Every orphan must get at least one inbound link.
            {note}
        </p>
        <button onclick="navigator.clipboard.writeText('{copy_text}')"
                style="background:linear-gradient(135deg,#005947,#00A868);color:#fff;border:none;
                       padding:8px 16px;border-radius:8px;font-family:'DM Sans',sans-serif;
                       font-size:13px;font-weight:600;cursor:pointer;margin-bottom:12px;">
            Copy all orphan URLs
        </button>
        {_table_html(["URL", "Status"], orphan_rows, max_height="400px")}
        """

    # --- AI Recommendations ---
    recs_section = ""
    if recommendations:
        n_high = sum(1 for r in recommendations if r.get("priority") == "high")
        n_med = sum(1 for r in recommendations if r.get("priority") == "medium")
        n_low = sum(1 for r in recommendations if r.get("priority") == "low")

        # Tag helpers (match the CSV/Excel behavior)
        orphan_set = {r["url"] for r in all_orphan_pages}
        priority_set = set(priority_health_df["URL"].tolist()) if priority_health_df is not None else set()

        def _status(u, is_fb):
            if is_fb:
                return "Fallback"
            if u in orphan_set:
                return "Orphan"
            if u in priority_set:
                return "Priority"
            return "Standard"

        def _tag(r, s):
            base = r.get("reason", "")
            if base.startswith("[Orphan target]") or base.startswith("[Priority target]") or base.startswith("[Fallback link]"):
                return base
            if s == "Orphan":
                return f"[Orphan target] {base}".strip()
            if s == "Priority":
                return f"[Priority target] {base}".strip()
            if s == "Fallback":
                return f"[Fallback link] {base}".strip()
            return base

        priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        from src.cleaning.language import extract_lang_segment as _section_code

        def _section(url: str) -> str:
            c = _section_code(url or "")
            return f"/{c}/" if c else "(root)"

        rec_rows = []
        for rec in recommendations:
            source = rec.get("source_url", "")
            status = _status(rec.get("target_url", ""), bool(rec.get("is_fallback")))
            rec_rows.append([
                priority_icons.get(rec.get("priority", ""), ""),
                source,
                rec.get("target_url", ""),
                rec.get("suggested_anchor", ""),
                status,
                _section(source),
                str(int(rec.get("relevance_score", 0))),
                _tag(rec, status),
            ])

        recs_section = f"""
        <h2 style="margin-top:48px;">AI Link Recommendations <span style="background:linear-gradient(135deg,#005947,#00A868);
            padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;vertical-align:middle;">AI</span></h2>
        <p style="color:#94A3B8;font-size:14px;margin-bottom:16px;">
            Found <strong style="color:#F0F4F8;">{len(recommendations)}</strong> opportunities:
            <span style="color:#F87171;font-weight:600;">{n_high} high</span>,
            <span style="color:#FBBF24;font-weight:600;">{n_med} medium</span>,
            <span style="color:#34D399;font-weight:600;">{n_low} low</span> priority.</p>
        {_table_html(["", "Source URL", "Target URL", "Anchor", "Target", "Section", "Score", "Reason"], rec_rows, max_height="600px")}
        """

    # --- C3 — Recurring-event redirect candidates ---
    redirect_section = ""
    if redirect_candidates:
        redirect_rows = []
        for cand in redirect_candidates:
            redirect_rows.append([
                cand.get("series", ""),
                str(cand.get("past_year", "")),
                cand.get("past_url", ""),
                "→",
                str(cand.get("current_year", "")),
                cand.get("current_url", ""),
            ])
        redirect_section = f"""
        <h2 style="margin-top:48px;">Past-edition redirect candidates</h2>
        <p style="color:#94A3B8;font-size:14px;margin-bottom:16px;">
            Found <strong style="color:#F0F4F8;">{len(redirect_candidates)}</strong>
            past-edition page(s) of recurring series that should
            <strong>301-redirect</strong> to the current edition. Implementing these
            consolidates ranking signals onto the current page.</p>
        {_table_html(["Series", "Past year", "Past URL", "", "Current year", "Current URL"], redirect_rows, max_height="500px")}
        """

    # --- Token usage ---
    token_section = ""
    if token_usage and token_usage.get("api_calls", 0) > 0:
        cost = (token_usage["prompt_tokens"] * 0.30 + (token_usage["completion_tokens"] + token_usage["thinking_tokens"]) * 2.50) / 1_000_000
        token_section = f"""
        <h2 style="margin-top:48px;">AI Token Usage <span style="background:linear-gradient(135deg,#005947,#00A868);
            padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;vertical-align:middle;">AI</span></h2>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;">
            {_stat_card_html(str(token_usage["api_calls"]), "API Calls")}
            {_stat_card_html(f'{token_usage["prompt_tokens"]:,}', "Input Tokens")}
            {_stat_card_html(f'{token_usage["completion_tokens"]:,}', "Output Tokens")}
            {_stat_card_html(f'{token_usage["thinking_tokens"]:,}', "Thinking Tokens")}
        </div>
        <p style="color:#64748B;font-size:12px;">
            Total: {token_usage["total_tokens"]:,} tokens. Estimated cost: ~${cost:.4f}</p>
        """

    # Merged orphan count (in-crawl + true orphans)
    all_orphan_count = audit.get("all_orphan_count", audit.get("orphan_count", 0))

    # --- Assemble HTML ---
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Internal Link Analysis — {site_domain} — {date_str}</title>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0B1621;
            color: #F0F4F8;
            padding: 40px 24px;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 4px;
        }}
        h1 span {{
            background: linear-gradient(135deg, #005947, #00A868, #00D68F);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        h2 {{
            font-family: 'Outfit', sans-serif;
            font-size: 22px;
            font-weight: 600;
            color: #F0F4F8;
            margin-bottom: 12px;
        }}
        .subtitle {{
            color: #94A3B8;
            font-size: 14px;
            margin-bottom: 32px;
        }}
        .header-line {{
            height: 3px;
            background: linear-gradient(90deg, #005947, #00A868, #00D68F);
            border-radius: 2px;
            margin-bottom: 32px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .section-desc {{
            color: #94A3B8;
            font-size: 14px;
            margin-bottom: 16px;
        }}
        .footer {{
            margin-top: 48px;
            padding-top: 20px;
            border-top: 1px solid rgba(37, 64, 85, 0.6);
            color: #64748B;
            font-size: 12px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1><span>Internal Link Analysis</span></h1>
        <p class="subtitle">
            <strong style="color:#F0F4F8;">{site_domain}</strong> &mdash;
            {date_str} at {time_str} &mdash;
            {audit["total_links"]:,} cleaned links across {audit["total_pages"]:,} pages
        </p>
        <div class="header-line"></div>

        <!-- Overview -->
        <h2>Overview</h2>
        <div class="stats-grid">
            {_stat_card_html(f'{audit["total_pages"]:,}', "Total Pages")}
            {_stat_card_html(f'{audit["total_links"]:,}', "Internal Links")}
            {_stat_card_html(f'{all_orphan_count:,}', "Orphan Pages", danger=all_orphan_count > 0)}
            {_stat_card_html(str(audit["inbound_avg"]), "Avg Inbound Links", accent=True)}
        </div>

        <div style="background:rgba(15,29,43,0.7);border:1px solid rgba(37,64,85,0.6);border-radius:12px;padding:20px;margin-bottom:24px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;color:#94A3B8;font-size:13px;">
                <div>
                    <strong style="color:#F0F4F8;">Inbound links per page</strong><br>
                    Average: <strong>{audit["inbound_avg"]}</strong> &bull;
                    Median: <strong>{audit["inbound_median"]}</strong><br>
                    Min: <strong>{audit["inbound_min"]}</strong> &bull;
                    Max: <strong>{audit["inbound_max"]}</strong>
                </div>
                <div>
                    <strong style="color:#F0F4F8;">Outbound links per page</strong><br>
                    Average: <strong>{audit["outbound_avg"]}</strong> &bull;
                    Median: <strong>{audit["outbound_median"]}</strong><br>
                    Min: <strong>{audit["outbound_min"]}</strong> &bull;
                    Max: <strong>{audit["outbound_max"]}</strong>
                </div>
            </div>
        </div>

        <!-- Orphan Pages list -->
        {orphan_section}

        <!-- PageRank Distribution -->
        <h2 style="margin-top:48px;">PageRank Distribution</h2>
        <p class="section-desc">How internal link equity is distributed across the site.</p>
        {plotly_chart_html}

        <!-- Top Pages by PageRank -->
        <h2 style="margin-top:48px;">Top Pages by PageRank</h2>
        <p class="section-desc">Pages with the most internal link equity — strongest authority pages.</p>
        {_table_html(["Rank", "URL", "PageRank Score"], top_pages_rows)}

        <!-- Priority URLs Health -->
        <h2 style="margin-top:48px;">Priority URLs Health</h2>
        <p class="section-desc">How well your priority pages are supported by internal links.</p>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">
            {_stat_card_html(str(n_critical), "Critical", danger=True)}
            {_stat_card_html(str(n_warning), "Warning")}
            {_stat_card_html(str(n_good), "Good", accent=True)}
        </div>
        {_table_html(["", "URL", "Target Keyword", "Content Type", "Inbound Links", "PageRank"], priority_rows)}

        <!-- Cocoon Health -->
        {cocoon_section}

        <!-- AI Recommendations -->
        {recs_section}

        <!-- Past-edition redirect candidates (C3) -->
        {redirect_section}

        <!-- Token Usage -->
        {token_section}

        <div class="footer">
            Internal Link Analyzer &mdash; Generated {date_str} at {time_str} &mdash; {site_domain}
        </div>
    </div>
</body>
</html>"""

    return html
