"""Internal Link Analyzer — Main Streamlit App."""

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import pandas as pd
import plotly.express as px

# Add src to path so imports work with `streamlit run src/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Bridge Streamlit Cloud secrets into env vars (so config.py picks them up)
for _key in ("GEMINI_API_KEY", "ILA_PASSWORD", "ILA_DEV_MODE", "GEMINI_MODEL"):
    if _key not in os.environ:
        try:
            os.environ[_key] = st.secrets[_key]
        except (KeyError, FileNotFoundError):
            pass

# Apply user-provided API key from session state (overrides secrets/env)
if "user_api_key" in st.session_state and st.session_state.user_api_key:
    os.environ["GEMINI_API_KEY"] = st.session_state.user_api_key

# Re-read config after env is set (config.py reads from os.environ at import time)
import importlib
import src.config
importlib.reload(src.config)

from src.config import APP_PASSWORD, GEMINI_API_KEY, HEALTH_CRITICAL_MAX, HEALTH_WARNING_MAX
from src.parsers.screaming_frog import parse_screaming_frog_csv
from src.parsers.priority_urls import parse_priority_urls_csv
from src.cleaning.link_position import get_position_summary, filter_by_positions
from src.cleaning.url_patterns import (
    detect_url_patterns, filter_by_patterns,
    detect_pagination_urls, filter_pagination,
    detect_template_links, filter_template_links,
    detect_news_patterns, filter_news_patterns,
)
from src.cleaning.language import (
    detect_languages, filter_by_language, detect_language_switchers, ROOT_KEY,
)
from src.analysis.cost_estimator import estimate_cost, format_cost
from src.analysis.link_audit import compute_link_audit, get_priority_urls_health
from src.analysis.pagerank import compute_pagerank, get_top_pages, get_pagerank_distribution
from src.analysis.ai_analyzer import run_ai_analysis, get_token_usage, check_api_health
from src.analysis.cocoon_health import analyze_cocoon_health
from src.export.csv_export import generate_linking_plan_csv
from src.ui.components import (
    apply_bc_theme,
    render_header,
    render_upload_confirmation,
    render_badge,
    render_stat_card,
    render_health_card,
    render_summary_box,
)

# Page config
st.set_page_config(
    page_title="Internal Link Analyzer",
    page_icon="🔗",
    layout="centered",
)

# Apply BC theme
apply_bc_theme()


# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = "upload"  # upload -> step1 -> step2 -> results
if "sf_data" not in st.session_state:
    st.session_state.sf_data = None
if "priority_data" not in st.session_state:
    st.session_state.priority_data = None
if "full_url_list" not in st.session_state:
    st.session_state.full_url_list = None
if "cleaned_data" not in st.session_state:
    st.session_state.cleaned_data = None
if "position_filtered_data" not in st.session_state:
    st.session_state.position_filtered_data = None
if "exclude_patterns" not in st.session_state:
    st.session_state.exclude_patterns = []
if "audit_results" not in st.session_state:
    st.session_state.audit_results = None
if "pagerank_scores" not in st.session_state:
    st.session_state.pagerank_scores = None
if "ai_results" not in st.session_state:
    st.session_state.ai_results = None
if "cocoon_health_data" not in st.session_state:
    st.session_state.cocoon_health_data = None
if "token_usage" not in st.session_state:
    st.session_state.token_usage = None
if "ai_health" not in st.session_state:
    st.session_state.ai_health = None  # None = not checked yet


def reset_analysis():
    """Clear all data and return to the upload screen."""
    for key in [
        "sf_data", "priority_data", "full_url_list", "cleaned_data", "position_filtered_data",
        "url_patterns", "position_keep", "pattern_exclude", "exclude_patterns",
        "custom_patterns", "pagination_info", "remove_pagination", "manual_excluded_urls",
        "template_links_info", "template_exclude",
        "language_info", "selected_language", "step2_lang_cache_key",
        "news_patterns_info", "news_exclude",
        "audit_results", "pagerank_scores", "ai_results", "cocoon_health_data", "token_usage",
        "ai_health", "market_resolved", "market_detection",
    ]:
        if key in st.session_state:
            if key == "exclude_patterns":
                st.session_state[key] = []
            else:
                st.session_state[key] = None
    st.session_state.wizard_step = "upload"


# ============================================================
# SCREEN 1: LOGIN
# ============================================================
def render_login():
    """Render the login screen — centered, standalone."""
    st.markdown("<br><br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<h1 class='login-title'>Internal Link Analyzer</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p class='login-subtitle'>"
            "Upload your Screaming Frog export and get<br>AI-powered linking recommendations</p>",
            unsafe_allow_html=True,
        )

        password = st.text_input("Password", type="password", label_visibility="collapsed",
                                  placeholder="Enter password")

        if st.button("Access", use_container_width=True):
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")


# ============================================================
# SCREEN 2: SETUP (upload + cleaning wizard)
# ============================================================
def render_setup_step_indicator():
    """Render the step indicator for the setup screen only."""
    steps = {
        "upload": 1,
        "step1": 2,
        "step2": 3,
    }
    current = steps.get(st.session_state.wizard_step, 1)

    step_labels = ["Upload", "Clean Links", "Review URLs"]
    cols = st.columns(len(step_labels) * 2 - 1)

    step_keys = ["upload", "step1", "step2"]

    for i, label in enumerate(step_labels):
        col_idx = i * 2
        step_num = i + 1
        with cols[col_idx]:
            if step_num < current:
                st.markdown(
                    f"<div class='step-done'>"
                    f"<span class='step-circle'>&#10003;</span>"
                    f"<br><span class='step-text'>{label}</span></div>",
                    unsafe_allow_html=True,
                )
            elif step_num == current:
                st.markdown(
                    f"<div class='step-active'>"
                    f"<span class='step-circle'>{step_num}</span>"
                    f"<br><span class='step-text'>{label}</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='step-future'>"
                    f"<span class='step-circle'>{step_num}</span>"
                    f"<br><span class='step-text'>{label}</span></div>",
                    unsafe_allow_html=True,
                )

        # Connecting line
        if i < len(step_labels) - 1:
            line_col_idx = col_idx + 1
            with cols[line_col_idx]:
                color = "#34D399" if step_num < current else "rgba(37, 64, 85, 0.6)"
                st.markdown(
                    f"<div style='border-top:2px solid {color};margin-top:14px;'></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("<br>", unsafe_allow_html=True)


def _parse_full_url_list(uploaded_file):
    """Parse a CSV/Excel file containing a list of all site URLs.

    Accepts a single-column file or multi-column — takes the first column
    that looks like URLs (contains 'http'). Returns a set of URLs.
    """
    import io

    try:
        content = uploaded_file.read()
        uploaded_file.seek(0)

        # Try CSV first
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception:
            df = pd.read_excel(io.BytesIO(content))

        if df.empty:
            return None, "File is empty"

        # Find the column with URLs
        url_col = None
        for col in df.columns:
            # Check if column name looks like a URL (headerless file)
            if str(col).startswith("http"):
                # The header itself is a URL — re-read without header
                try:
                    df = pd.read_csv(io.BytesIO(content), header=None)
                except Exception:
                    df = pd.read_excel(io.BytesIO(content), header=None)
                url_col = 0
                break
            # Check if column contents contain URLs
            sample = df[col].dropna().head(5).astype(str)
            if sample.str.contains("http", case=False).any():
                url_col = col
                break

        if url_col is None:
            # Fall back to first column
            url_col = df.columns[0]

        urls = df[url_col].dropna().astype(str).str.strip()
        urls = urls[urls.str.startswith("http")]

        if len(urls) == 0:
            return None, "No valid URLs found (URLs should start with http)"

        return set(urls.tolist()), None

    except Exception as e:
        return None, f"Could not read file: {e}"


def _upload_label(title, hint, required=True):
    """Render a compact upload field label."""
    opt = ("" if required
           else "<span style='color:#64748B;font-size:11px;font-weight:400;"
                "margin-left:6px;'>optional</span>")
    st.markdown(
        f"<p style='margin:0 0 2px 0;'>"
        f"<span style='color:#F0F4F8;font-family:Outfit,sans-serif;font-size:13px;"
        f"font-weight:600;'>{title}</span>{opt}</p>"
        f"<p style='color:#64748B;font-size:12px;margin:0 0 6px 0;'>{hint}</p>",
        unsafe_allow_html=True,
    )


def render_upload():
    """Render the file upload section — each field in its own container."""
    st.markdown("## Upload your files")

    # --- 1. Screaming Frog Export ---
    with st.container(border=True):
        _upload_label(
            "Screaming Frog Export",
            "Bulk Export → All Inlinks (.csv)",
        )
        sf_file = st.file_uploader(
            "Screaming Frog CSV",
            type=["csv"],
            key="sf_upload",
            label_visibility="collapsed",
        )

        if sf_file is not None and st.session_state.sf_data is None:
            df, error = parse_screaming_frog_csv(sf_file)
            if error:
                st.error(f"Screaming Frog CSV error: {error}")
            else:
                st.session_state.sf_data = df

        if st.session_state.sf_data is not None:
            render_upload_confirmation(
                sf_file.name if sf_file else "Screaming Frog CSV",
                f"{len(st.session_state.sf_data):,} hyperlink rows loaded",
            )

    # --- 2. Priority URLs ---
    with st.container(border=True):
        _upload_label(
            "Priority URLs",
            "CSV with columns: URL, Target Keyword, Content Type (optional)",
        )
        priority_file = st.file_uploader(
            "Priority URLs CSV",
            type=["csv"],
            key="priority_upload",
            label_visibility="collapsed",
        )
        template_csv = "URL,Target Keyword,Content Type\nhttps://example.com/promo-code-operator,promo code operator,code page\nhttps://example.com/best-betting-sites,best betting sites,comparator\nhttps://example.com/operator-review,operator review,review\n"
        st.download_button(
            label="Download template",
            data=template_csv,
            file_name="priority-urls-template.csv",
            mime="text/csv",
            key="template_download",
        )

        if priority_file is not None and st.session_state.priority_data is None:
            df, error = parse_priority_urls_csv(priority_file)
            if error:
                st.error(f"Priority URLs CSV error: {error}")
            else:
                st.session_state.priority_data = df

        if st.session_state.priority_data is not None:
            priority_df = st.session_state.priority_data
            ct_count = (priority_df["Content Type"] != "").sum()
            detail = f"{len(priority_df):,} URLs loaded"
            if ct_count > 0:
                detail += f" ({ct_count} with content type)"
            render_upload_confirmation(
                priority_file.name if priority_file else "Priority URLs CSV",
                detail,
            )

    # --- 3. Full Site URL List (optional) ---
    with st.container(border=True):
        _upload_label(
            "Full Site URL List",
            "All site URLs — detects true orphan pages not found in the crawl",
            required=False,
        )
        url_list_file = st.file_uploader(
            "Full URL List",
            type=["csv", "xlsx", "xls"],
            key="url_list_upload",
            label_visibility="collapsed",
        )

        if url_list_file is not None and st.session_state.full_url_list is None:
            url_set, error = _parse_full_url_list(url_list_file)
            if error:
                st.error(f"URL list error: {error}")
            else:
                st.session_state.full_url_list = url_set

        if st.session_state.full_url_list is not None:
            render_upload_confirmation(
                url_list_file.name if url_list_file else "Full URL List",
                f"{len(st.session_state.full_url_list):,} URLs loaded",
            )

    # Determine if ready to proceed
    files_ready = st.session_state.sf_data is not None and st.session_state.priority_data is not None
    ai_health = st.session_state.get("ai_health")
    ai_ok = ai_health and ai_health.get("ok", False)
    can_proceed = files_ready and ai_ok

    # Sticky bottom bar — always visible, disabled until ready
    with st._bottom:
        if not files_ready:
            hint = "Upload Screaming Frog export and Priority URLs to continue"
        elif not ai_ok:
            hint = "Connect the Gemini API to continue"
        else:
            hint = None
        if hint:
            st.markdown(
                f"<p style='color:#64748B;font-size:12px;text-align:center;margin:0 0 6px 0;'>{hint}</p>",
                unsafe_allow_html=True,
            )
        if st.button("Next →", use_container_width=True, disabled=not can_proceed):
            st.session_state.wizard_step = "step1"
            st.rerun()

    # Cross-check priority URLs against crawl data
    if st.session_state.sf_data is not None and st.session_state.priority_data is not None:
        sf_df = st.session_state.sf_data
        priority_df = st.session_state.priority_data

        # All URLs found in the crawl (sources + destinations)
        crawl_urls = set(sf_df["Source"].tolist() + sf_df["Destination"].tolist())
        priority_urls = set(priority_df["URL"].tolist())

        matched = priority_urls & crawl_urls
        unmatched = priority_urls - crawl_urls
        match_pct = len(matched) / len(priority_urls) * 100 if priority_urls else 0

        st.markdown("<br>", unsafe_allow_html=True)

        if len(unmatched) == 0:
            st.markdown(
                f"<div class='url-match-ok'>&#10003; All <strong>{len(matched)}</strong> priority URLs "
                f"found in the crawl data — ready to analyze.</div>",
                unsafe_allow_html=True,
            )
        elif match_pct >= 50:
            st.markdown(
                f"<div class='url-match-warn'>&#9888; <strong>{len(matched)}/{len(priority_urls)}</strong> "
                f"priority URLs found in the crawl ({match_pct:.0f}% match). "
                f"<strong>{len(unmatched)}</strong> URL(s) not found — they may be new pages, "
                f"misspelled, or not yet crawled.</div>",
                unsafe_allow_html=True,
            )
            with st.expander(f"Show {len(unmatched)} unmatched URL(s)"):
                for url in sorted(unmatched):
                    st.markdown(
                        f"<p style='font-family:\"JetBrains Mono\",monospace;font-size:12px;"
                        f"color:#FBBF24;padding:2px 0;'>{url}</p>",
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                f"<div class='url-match-err'>&#10007; Only <strong>{len(matched)}/{len(priority_urls)}</strong> "
                f"priority URLs found in the crawl ({match_pct:.0f}% match). "
                f"Most of your priority URLs don't exist in the Screaming Frog export. "
                f"Check that both files are from the <strong>same site</strong>.</div>",
                unsafe_allow_html=True,
            )
            with st.expander(f"Show {len(unmatched)} unmatched URL(s)"):
                for url in sorted(unmatched):
                    st.markdown(
                        f"<p style='font-family:\"JetBrains Mono\",monospace;font-size:12px;"
                        f"color:#F87171;padding:2px 0;'>{url}</p>",
                        unsafe_allow_html=True,
                    )

        if not ai_ok:
            st.markdown(
                "<div style='background:rgba(248,113,113,0.1);border:1px solid #F87171;"
                "border-radius:8px;padding:12px 16px;margin-bottom:12px;'>"
                "<p style='color:#F87171;font-size:14px;font-weight:600;margin:0 0 4px 0;'>"
                "AI is not connected</p>"
                "<p style='color:#FDA4AF;font-size:13px;margin:0;'>"
                "Scroll up to the AI configuration panel, paste a valid Gemini API key, "
                "and click Connect before continuing.</p></div>",
                unsafe_allow_html=True,
            )


def render_cleaning_step1():
    """Render Step 1 of the cleaning wizard — filter by link position."""
    st.markdown(
        f"## Clean Links {render_badge('Step 1')}",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94A3B8;font-size:14px;margin-bottom:6px;'>"
        "Not all links carry SEO value. Navigation, header, and footer links are structural — "
        "we only want <strong style='color:#34D399;'>Content</strong> links for analysis.</p>"
        "<p style='color:#94A3B8;font-size:13px;margin-bottom:24px;'>"
        "We recommend keeping only <strong style='color:#F0F4F8;'>Content</strong>. "
        "Uncheck anything you don't need.</p>",
        unsafe_allow_html=True,
    )

    df = st.session_state.sf_data
    summary = get_position_summary(df)

    # Initialize keep state
    if "position_keep" not in st.session_state:
        st.session_state.position_keep = {
            row["Position"]: row["Action"] == "Keep"
            for _, row in summary.iterrows()
        }

    # Interactive table — toggle Keep directly in the table
    edit_df = summary[["Position", "Count"]].copy()
    edit_df["Count"] = edit_df["Count"].astype(int)
    edit_df["Keep"] = edit_df["Position"].map(st.session_state.position_keep).fillna(False).astype(bool)

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Position": st.column_config.TextColumn("Link Position", disabled=True, width="medium"),
            "Count": st.column_config.NumberColumn("Links Found", format="%d", disabled=True),
            "Keep": st.column_config.CheckboxColumn("Keep"),
        },
        key="position_editor",
    )

    # Update state from table edits
    for _, row in edited.iterrows():
        st.session_state.position_keep[row["Position"]] = row["Keep"]

    # Summary
    keep_positions = [p for p, keep in st.session_state.position_keep.items() if keep]
    keep_count = summary[summary["Position"].isin(keep_positions)]["Count"].sum()
    remove_count = summary["Count"].sum() - keep_count

    render_summary_box(
        f"Keeping <strong>{keep_count:,}</strong> links &mdash; "
        f"removing <strong>{remove_count:,}</strong> non-content links"
    )

    # Block Step 2 if Link Path column is missing — template-link detection needs it
    link_path_missing = "Link Path" not in df.columns
    if link_path_missing:
        st.markdown(
            "<div style='background:rgba(248,113,113,0.12);border:1px solid rgba(248,113,113,0.4);"
            "border-radius:8px;padding:12px 16px;margin-top:16px;'>"
            "<p style='color:#F87171;font-size:14px;font-weight:600;margin:0 0 4px 0;'>"
            "⚠️ Missing <code>Link Path</code> column</p>"
            "<p style='color:#FECACA;font-size:13px;margin:0 0 4px 0;'>"
            "Your Screaming Frog export doesn't include the <code>Link Path</code> (XPath) column. "
            "Without it, we can't detect template links misclassified as <code>Content</code> — a key "
            "cleaning step for sites with non-semantic HTML.</p>"
            "<p style='color:#FECACA;font-size:13px;margin:0;'>"
            "<strong>Fix:</strong> In Screaming Frog → Configuration → Spider → Extraction → "
            "enable <strong>Store HTML</strong> and <strong>Link Paths</strong>, then re-crawl and re-export.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    # Sticky bottom action bar
    with st._bottom:
        bar_cols = st.columns([1, 3])
        with bar_cols[0]:
            if st.button("← Back to Upload", key="step1_back", type="tertiary"):
                st.session_state.wizard_step = "upload"
                st.rerun()
        with bar_cols[1]:
            if link_path_missing:
                st.button(
                    "Apply & Next →  (blocked: Link Path column missing)",
                    key="step1_next",
                    use_container_width=True,
                    disabled=True,
                )
            else:
                if st.button("Apply & Next →", key="step1_next", use_container_width=True):
                    filtered = filter_by_positions(df, keep_positions)
                    st.session_state.position_filtered_data = filtered
                    st.session_state.wizard_step = "step2"
                    st.rerun()


def _apply_step2_filters(df: pd.DataFrame, exclude_patterns: list[str]) -> pd.DataFrame:
    """Apply every Step 2 filter to df in the order they appear in the UI.

    Pre-conditions: df is already language-filtered (the caller passes the
    rendered Step 2 df, not raw `position_filtered_data`). Filters here are
    additive — pagination, news, template, URL pattern, manual URL excludes.
    """
    cleaned = filter_by_patterns(df, exclude_patterns) if exclude_patterns else df.copy()

    pagination = st.session_state.get("pagination_info") or {}
    if (
        st.session_state.get("remove_pagination", False)
        and pagination.get("count", 0) > 0
    ):
        cleaned = filter_pagination(cleaned, pagination["urls"])

    news_info = st.session_state.get("news_patterns_info") or {"patterns": []}
    news_excl_map = st.session_state.get("news_exclude", {})
    news_excl_urls: set[str] = set()
    for pat in news_info.get("patterns", []):
        if news_excl_map.get(pat["label"], False):
            news_excl_urls |= pat["urls"]
    if news_excl_urls:
        cleaned = filter_news_patterns(cleaned, news_excl_urls)

    template_excl = [
        p for p, excl in st.session_state.get("template_exclude", {}).items() if excl
    ]
    if template_excl:
        cleaned = filter_template_links(cleaned, template_excl)

    manual_set = st.session_state.get("manual_excluded_urls") or set()
    if manual_set:
        mask = cleaned["Source"].isin(manual_set) | cleaned["Destination"].isin(manual_set)
        cleaned = cleaned[~mask].copy()

    return cleaned


def _render_cost_estimate(remaining_url_count: int):
    """Render the pre-run cost estimate panel above the Run Analysis bar."""
    from src import config as _config
    model = _config.GEMINI_MODEL
    est = estimate_cost(remaining_url_count, model=model)

    cost_str = format_cost(est["total_cost"])
    cap_note = ""
    if est["page_cap_applied"]:
        cap_note = (
            f"<div style='font-size:12px;color:#94A3B8;margin-top:4px;'>"
            f"AI page cap is {est['capped_pages']:,} (selected by priority + orphans + top PageRank). "
            f"The estimate uses the capped count, not the {remaining_url_count:,} total.</div>"
        )

    unknown_note = ""
    if not est["is_known_model"]:
        unknown_note = (
            "<div style='font-size:12px;color:#FBBF24;margin-top:4px;'>"
            f"Cost for <code>{model}</code> is extrapolated from the closest known family — "
            "treat as a rough estimate.</div>"
        )

    color = "#34D399"  # green by default
    if est["total_cost"] >= 1:
        color = "#FBBF24"  # amber when ≥$1
    if est["total_cost"] >= 5:
        color = "#F87171"  # red when ≥$5

    st.markdown(
        f"<div style='border:1px solid rgba(148,163,184,0.2);border-radius:10px;"
        f"padding:14px 18px;margin:18px 0 6px;background:rgba(15,23,42,0.4);'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;'>"
        f"<div>"
        f"<div style='font-size:13px;color:#94A3B8;text-transform:uppercase;letter-spacing:0.06em;'>"
        f"Estimated AI cost</div>"
        f"<div style='font-size:11px;color:#64748B;margin-top:2px;'>"
        f"{est['capped_pages']:,} pages · {est['total_calls']} API calls · "
        f"<code>{model}</code></div>"
        f"</div>"
        f"<div style='font-size:28px;font-weight:600;color:{color};font-family:JetBrains Mono,monospace;'>"
        f"~{cost_str}</div>"
        f"</div>"
        f"{cap_note}"
        f"{unknown_note}"
        f"<div style='font-size:11px;color:#64748B;margin-top:6px;'>"
        f"Empirical estimate — actual cost can vary ±30%. To lower it: tighten exclusions, "
        f"pick a smaller language section, or switch to a cheaper model in the AI panel.</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _step2_clear_section_caches():
    """Clear cached Step 2 detections so they re-run on a re-filtered df."""
    for k in (
        "pagination_info", "template_links_info", "template_exclude",
        "url_patterns", "pattern_exclude", "news_patterns_info", "news_exclude",
        "manual_excluded_urls",
    ):
        st.session_state.pop(k, None)


def render_cleaning_step2():
    """Render Step 2 of the cleaning wizard — filter URL patterns."""
    st.markdown(
        f"## Review URLs {render_badge('Step 2')}",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94A3B8;font-size:14px;margin-bottom:6px;'>"
        "We detected URL patterns on your site. Exclude the ones that aren't real content pages — "
        "pagination, tags, author pages, etc.</p>"
        "<p style='color:#94A3B8;font-size:13px;margin-bottom:24px;'>"
        "When in doubt, <strong style='color:#F0F4F8;'>leave unchecked</strong> — you can always re-run later.</p>",
        unsafe_allow_html=True,
    )

    raw_df = st.session_state.position_filtered_data

    # ---- Language detection + selector (Phase 11 / A4) ------------------------
    # Detect once per session and cache. The detection result holds a url -> lang
    # map we reuse for fast filtering and language-switcher detection.
    if "language_info" not in st.session_state:
        st.session_state.language_info = detect_languages(raw_df)

    lang_info = st.session_state.language_info
    detected_langs = lang_info["languages"]
    root_section = lang_info["root"]

    multilingual = len(detected_langs) >= 2 or (len(detected_langs) >= 1 and root_section)

    if multilingual:
        st.markdown("#### Language section", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#94A3B8;font-size:14px;margin-bottom:12px;'>"
            "Your site has multiple language sections. Pick one to analyze. "
            "<span style='color:#64748B;'>(Phase B will support running all languages in one pass.)</span></p>",
            unsafe_allow_html=True,
        )

        options: list[tuple[str, str]] = []  # (code, display label)
        for lang in detected_langs:
            display = (
                f"{lang['label']} — {lang['page_count']:,} pages, "
                f"{lang['link_count']:,} links"
            )
            options.append((lang["code"], display))
        if root_section:
            display = (
                f"{root_section['label']} — {root_section['page_count']:,} pages, "
                f"{root_section['link_count']:,} links"
            )
            options.append((ROOT_KEY, display))

        # Default to the largest section the first time we render.
        if "selected_language" not in st.session_state or st.session_state.selected_language is None:
            st.session_state.selected_language = options[0][0]

        codes = [c for c, _ in options]
        labels = [l for _, l in options]
        try:
            current_idx = codes.index(st.session_state.selected_language)
        except ValueError:
            current_idx = 0
            st.session_state.selected_language = codes[0]

        chosen_label = st.selectbox(
            "Pick a language section",
            options=labels,
            index=current_idx,
            key="language_selector",
            label_visibility="collapsed",
        )
        chosen_code = codes[labels.index(chosen_label)]

        if chosen_code != st.session_state.selected_language:
            st.session_state.selected_language = chosen_code
            _step2_clear_section_caches()
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
    else:
        # Single-language site — no selector needed, but keep state consistent.
        if detected_langs:
            st.session_state.selected_language = detected_langs[0]["code"]
        elif root_section:
            st.session_state.selected_language = ROOT_KEY
        else:
            st.session_state.selected_language = None

    # Apply the language filter so every downstream detector runs on the
    # selected section only (cocoon detection, news, template, patterns).
    if st.session_state.get("selected_language"):
        df = filter_by_language(
            raw_df,
            st.session_state.selected_language,
            url_lang_map=lang_info["url_lang_map"],
        )
    else:
        df = raw_df

    # ---- Pagination detection ----
    if "pagination_info" not in st.session_state:
        st.session_state.pagination_info = detect_pagination_urls(df)
    if "remove_pagination" not in st.session_state:
        st.session_state.remove_pagination = True

    pagination = st.session_state.pagination_info
    if pagination["count"] > 0:
        st.markdown(
            f"#### Pagination detected",
            unsafe_allow_html=True,
        )
        patterns_str = ", ".join(f"`{p}`" for p in pagination["patterns_found"])
        st.markdown(
            f"<p style='color:#94A3B8;font-size:14px;margin-bottom:12px;'>"
            f"Found <strong style='color:#FFFFFF;'>{pagination['count']:,}</strong> paginated URLs "
            f"({pagination['link_count']:,} links) matching patterns: {patterns_str}</p>",
            unsafe_allow_html=True,
        )

        # Show examples
        if pagination["examples"]:
            examples_html = "".join(
                f"<div style='font-family:JetBrains Mono,monospace;font-size:12px;color:#64748B;padding:2px 0;'>{url}</div>"
                for url in pagination["examples"]
            )
            if pagination["count"] > 5:
                examples_html += (
                    f"<div style='font-size:12px;color:#64748B;padding:2px 0;'>"
                    f"... and {pagination['count'] - 5:,} more</div>"
                )
            st.markdown(examples_html, unsafe_allow_html=True)

        st.session_state.remove_pagination = st.checkbox(
            f"Remove pagination URLs ({pagination['count']:,} URLs, {pagination['link_count']:,} links)",
            value=st.session_state.remove_pagination,
            key="pagination_toggle",
        )
        st.markdown("<br>", unsafe_allow_html=True)

    # ---- Template link detection (false "Content" links) ----
    # Note: language-switcher detection (A5) runs on the *raw* (pre-language-filter)
    # df — switcher links typically point cross-language and would disappear from
    # `df` after filter_by_language. The result is merged into the template list so
    # the switcher path is excluded *before* the language filter (which is fine —
    # exclude_patterns / template filtering apply to raw_df at Run-Analysis time).
    if "template_links_info" not in st.session_state:
        tpl = detect_template_links(df)
        switchers = []
        if multilingual:
            lang_codes = [l["code"] for l in detected_langs]
            switchers = detect_language_switchers(raw_df, lang_codes)
        existing_paths = {p["path"] for p in tpl["paths"]}
        switcher_paths = set()
        for sw in switchers:
            switcher_paths.add(sw["path"])
            if sw["path"] in existing_paths:
                # Tag the existing entry so the UI shows the switcher badge
                for p in tpl["paths"]:
                    if p["path"] == sw["path"]:
                        p["is_language_switcher"] = True
                        p["target_languages"] = sw["target_languages"]
                        break
            else:
                # Path didn't qualify under generic template thresholds — add it
                tpl["paths"].append({
                    "path": sw["path"],
                    "anchors": [],
                    "destinations": sw["destinations"][:2],
                    "page_count": sw["page_count"],
                    "page_ratio": sw["page_ratio"],
                    "link_count": sw["link_count"],
                    "is_language_switcher": True,
                    "target_languages": sw["target_languages"],
                })
                tpl["total_links"] += sw["link_count"]
                tpl["total_paths"] += 1
        # Sort: switchers first (they're the most confident exclude), then by page count
        tpl["paths"].sort(
            key=lambda p: (not p.get("is_language_switcher", False), -p["page_count"])
        )
        st.session_state.template_links_info = tpl
    if "template_exclude" not in st.session_state:
        st.session_state.template_exclude = {
            p["path"]: True for p in st.session_state.template_links_info["paths"]
        }

    template_info = st.session_state.template_links_info
    if template_info["total_paths"] > 0:
        st.markdown("#### Template links misclassified as content", unsafe_allow_html=True)
        st.markdown(
            f"<p style='color:#94A3B8;font-size:14px;margin-bottom:6px;'>"
            f"Found <strong style='color:#FFFFFF;'>{template_info['total_paths']}</strong> XPath(s) "
            f"appearing on a high share of pages — likely nav/sidebar/footer templates that Screaming Frog "
            f"labeled as <code>Content</code> because the HTML isn't semantic (e.g. <code>&lt;div&gt;</code> "
            f"instead of <code>&lt;nav&gt;</code>).</p>"
            f"<p style='color:#94A3B8;font-size:13px;margin-bottom:12px;'>"
            f"Check = exclude these links from analysis. Uncheck only if the XPath really is editorial content "
            f"(rare).</p>",
            unsafe_allow_html=True,
        )

        for idx, path_info in enumerate(template_info["paths"]):
            path = path_info["path"]
            default_exclude = st.session_state.template_exclude.get(path, True)
            col1, col2, col3 = st.columns([0.5, 4, 1.2])
            with col1:
                st.session_state.template_exclude[path] = st.checkbox(
                    "Exclude",
                    value=default_exclude,
                    key=f"tpl_{idx}",
                    label_visibility="collapsed",
                )
            with col2:
                anchors_preview = ", ".join(f'"{a}"' for a in path_info["anchors"][:3] if a)
                dest_preview = path_info["destinations"][0] if path_info["destinations"] else ""
                switcher_badge = ""
                if path_info.get("is_language_switcher"):
                    targets = path_info.get("target_languages", [])
                    targets_str = ", ".join(f"/{c}/" for c in targets[:6])
                    if len(targets) > 6:
                        targets_str += f", +{len(targets) - 6} more"
                    switcher_badge = (
                        "<span style='display:inline-block;background:rgba(45,212,191,0.14);"
                        "border:1px solid rgba(45,212,191,0.4);color:#5EEAD4;font-size:11px;"
                        "padding:1px 8px;border-radius:4px;margin-bottom:4px;font-weight:600;'>"
                        f"Language switcher → {targets_str}</span><br>"
                    )
                st.markdown(
                    f"{switcher_badge}"
                    f"<div style='font-family:JetBrains Mono,monospace;font-size:12px;color:#F0F4F8;"
                    f"word-break:break-all;'>{path}</div>"
                    f"<div style='font-size:12px;color:#64748B;margin-top:2px;'>"
                    f"Top anchors: {anchors_preview or '—'}</div>"
                    f"<div style='font-size:12px;color:#64748B;'>"
                    f"Top dest: <span style='font-family:JetBrains Mono,monospace;'>{dest_preview}</span></div>",
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f"<span style='color:#94A3B8;font-size:13px;'>"
                    f"{path_info['page_count']:,} pages ({path_info['page_ratio']*100:.0f}%)<br>"
                    f"{path_info['link_count']:,} links</span>",
                    unsafe_allow_html=True,
                )
        st.markdown("<br>", unsafe_allow_html=True)

    # ---- News / timely URL detection (Phase 11 / A6) --------------------------
    if "news_patterns_info" not in st.session_state:
        st.session_state.news_patterns_info = detect_news_patterns(df)
    if "news_exclude" not in st.session_state:
        st.session_state.news_exclude = {
            p["label"]: True for p in st.session_state.news_patterns_info["patterns"]
        }
    news_info = st.session_state.news_patterns_info
    if news_info["patterns"]:
        st.markdown("#### News / timely content", unsafe_allow_html=True)
        st.markdown(
            f"<p style='color:#94A3B8;font-size:14px;margin-bottom:6px;'>"
            f"Found <strong style='color:#FFFFFF;'>{news_info['total_urls']:,}</strong> "
            f"time-sensitive URLs (news, match coverage, blog posts, dated slugs). "
            f"These usually shouldn't anchor evergreen linking.</p>"
            f"<p style='color:#94A3B8;font-size:13px;margin-bottom:12px;'>"
            f"Check = exclude from analysis. Uncheck if a section is actually evergreen.</p>",
            unsafe_allow_html=True,
        )
        for idx, pat in enumerate(news_info["patterns"]):
            label = pat["label"]
            default_exclude = st.session_state.news_exclude.get(label, True)
            col1, col2, col3 = st.columns([0.5, 4, 1.2])
            with col1:
                st.session_state.news_exclude[label] = st.checkbox(
                    "Exclude",
                    value=default_exclude,
                    key=f"news_{idx}",
                    label_visibility="collapsed",
                )
            with col2:
                st.markdown(
                    f"<div style='font-family:JetBrains Mono,monospace;font-size:13px;color:#F0F4F8;'>"
                    f"{label}</div>"
                    f"<div style='font-size:12px;color:#64748B;margin-top:2px;word-break:break-all;'>"
                    f"e.g. {pat['example']}</div>",
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f"<span style='color:#94A3B8;font-size:13px;'>"
                    f"{pat['url_count']:,} URLs<br>{pat['link_count']:,} links</span>",
                    unsafe_allow_html=True,
                )
        st.markdown("<br>", unsafe_allow_html=True)

    # Detect patterns (cached)
    if "url_patterns" not in st.session_state:
        st.session_state.url_patterns = detect_url_patterns(df)

    patterns_df = st.session_state.url_patterns

    if patterns_df.empty:
        st.info("No recurring URL patterns detected. All links will be included.")
        # Show the cost estimate even when no URL patterns exist (language /
        # news / template exclusions still affect the page count)
        unique_pages_count = pd.concat([df["Source"], df["Destination"]]).nunique()
        _render_cost_estimate(unique_pages_count)
        with st._bottom:
            bar_cols = st.columns([1, 3])
            with bar_cols[0]:
                if st.button("← Back to Clean Links", key="step2_empty_back", type="tertiary"):
                    st.session_state.wizard_step = "step1"
                    st.rerun()
            with bar_cols[1]:
                if st.button("Run Analysis →", key="step2_empty_next", use_container_width=True):
                    cleaned = _apply_step2_filters(df, [])
                    st.session_state.cleaned_data = cleaned
                    _start_analysis()
        return

    # Pattern toggles — check = exclude
    if "pattern_exclude" not in st.session_state:
        st.session_state.pattern_exclude = {
            row["Pattern"]: row["Exclude"]
            for _, row in patterns_df.iterrows()
        }

    st.markdown(
        "<p style='color:#94A3B8;font-size:13px;margin-bottom:12px;'>"
        "Check = exclude from analysis. Typical excludes: pagination, tags, author pages, categories.</p>",
        unsafe_allow_html=True,
    )

    for _, row in patterns_df.iterrows():
        pattern = row["Pattern"]
        default_exclude = st.session_state.pattern_exclude.get(pattern, row["Exclude"])
        col1, col2, col3, col4 = st.columns([0.5, 3, 0.8, 0.8])
        with col1:
            st.session_state.pattern_exclude[pattern] = st.checkbox(
                "Exclude",
                value=default_exclude,
                key=f"pat_{pattern}",
                label_visibility="collapsed",
            )
        with col2:
            st.markdown(
                f"**{pattern}**<br>"
                f"<span style='font-family:JetBrains Mono,monospace;font-size:12px;color:#64748B;'>"
                f"{row['Example']}</span>",
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                f"<span style='color:#94A3B8;font-size:13px;'>{row['URLs']:,} URLs</span>",
                unsafe_allow_html=True,
            )
        with col4:
            st.markdown(
                f"<span style='color:#94A3B8;font-size:13px;'>{row['Links']:,} links</span>",
                unsafe_allow_html=True,
            )

    # Custom pattern input
    st.markdown("<br>", unsafe_allow_html=True)

    # Initialize custom patterns list
    if "custom_patterns" not in st.session_state:
        st.session_state.custom_patterns = []

    st.markdown(
        "<p style='color:#F0F4F8;font-size:14px;font-weight:600;margin-bottom:2px;'>"
        "Add custom exclusion pattern</p>"
        "<p style='color:#94A3B8;font-size:13px;margin-bottom:8px;'>"
        "Path prefix like <code>/mx/category/</code> or text fragment like <code>-x-</code> "
        "to match anywhere in the URL.</p>",
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns([3, 1])
    with col1:
        custom = st.text_input(
            "Add custom pattern",
            placeholder="e.g. /mx/category/  or  -x-",
            label_visibility="collapsed",
            key="custom_pattern_input",
        )
    with col2:
        if st.button("+ Add", key="add_custom_pattern"):
            if custom:
                # Path prefix patterns start with / and get a wildcard suffix
                pattern = custom
                if pattern.startswith("/"):
                    if not pattern.endswith("*"):
                        pattern = pattern.rstrip("/") + "/*"
                # Count matches
                all_check_urls = set(df["Source"].tolist() + df["Destination"].tolist())
                if pattern.startswith("/"):
                    prefix = pattern.rstrip("*").rstrip("/")
                    match_count = sum(1 for u in all_check_urls if urlparse(u).path.rstrip("/").startswith(prefix))
                    mask = df["Source"].apply(lambda u: urlparse(u).path.rstrip("/").startswith(prefix)) | \
                           df["Destination"].apply(lambda u: urlparse(u).path.rstrip("/").startswith(prefix))
                else:
                    match_count = sum(1 for u in all_check_urls if pattern in u)
                    mask = df["Source"].str.contains(pattern, na=False, regex=False) | \
                           df["Destination"].str.contains(pattern, na=False, regex=False)
                match_links = int(mask.sum())
                # Add to custom patterns and to exclusion dict
                if pattern not in [p["pattern"] for p in st.session_state.custom_patterns]:
                    st.session_state.custom_patterns.append({
                        "pattern": pattern,
                        "urls": match_count,
                        "links": match_links,
                    })
                    st.session_state.pattern_exclude[pattern] = True
                st.rerun()

    # Show custom patterns as tags below the input
    if st.session_state.custom_patterns:
        tags_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;'>"
        for cp in st.session_state.custom_patterns:
            tags_html += (
                f"<span style='display:inline-flex;align-items:center;gap:6px;"
                f"background:rgba(248,113,113,0.12);border:1px solid rgba(248,113,113,0.3);"
                f"border-radius:6px;padding:4px 10px;font-size:12px;color:#F87171;"
                f"font-family:\"JetBrains Mono\",monospace;'>"
                f"{cp['pattern']}"
                f"<span style='color:#64748B;font-size:11px;'>"
                f"({cp['urls']:,} URLs, {cp['links']:,} links)</span>"
                f"</span>"
            )
        tags_html += "</div>"
        st.markdown(tags_html, unsafe_allow_html=True)

        # Remove buttons — one per custom pattern
        to_remove = None
        remove_cols = st.columns(len(st.session_state.custom_patterns))
        for idx, cp in enumerate(st.session_state.custom_patterns):
            with remove_cols[idx]:
                if st.button(f"Remove {cp['pattern']}", key=f"rm_custom_{idx}", type="tertiary"):
                    to_remove = idx
        if to_remove is not None:
            removed = st.session_state.custom_patterns.pop(to_remove)
            st.session_state.pattern_exclude.pop(removed["pattern"], None)
            st.rerun()

    # ---- Compute remaining URLs after pattern + pagination exclusions ----
    st.markdown("<br>", unsafe_allow_html=True)

    all_urls = sorted(set(
        df["Source"].tolist() + df["Destination"].tolist()
    ))
    total_url_count = len(all_urls)

    # Apply pattern exclusions (supports both path prefixes and substring patterns)
    exclude_patterns = [p for p, excl in st.session_state.pattern_exclude.items() if excl]
    if exclude_patterns:
        from src.cleaning.url_patterns import is_substring_pattern
        exclude_prefixes = [p.rstrip("*").rstrip("/") for p in exclude_patterns if not is_substring_pattern(p)]
        exclude_substrings = [p for p in exclude_patterns if is_substring_pattern(p)]
        all_urls = [
            u for u in all_urls
            if not any(urlparse(u).path.rstrip("/").startswith(px) for px in exclude_prefixes)
            and not any(sub in u for sub in exclude_substrings)
        ]

    # Apply pagination exclusions
    if st.session_state.get("remove_pagination", False) and pagination["count"] > 0:
        pagination_set = pagination["urls"]
        all_urls = [u for u in all_urls if u not in pagination_set]

    # Apply news/timely exclusions
    news_exclude_urls: set[str] = set()
    for pat in news_info["patterns"]:
        if st.session_state.news_exclude.get(pat["label"], False):
            news_exclude_urls |= pat["urls"]
    if news_exclude_urls:
        all_urls = [u for u in all_urls if u not in news_exclude_urls]

    # Apply manual URL exclusions from the browser
    if "manual_excluded_urls" not in st.session_state:
        st.session_state.manual_excluded_urls = set()
    manual_excluded = st.session_state.manual_excluded_urls
    if manual_excluded:
        all_urls = [u for u in all_urls if u not in manual_excluded]

    # ---- Total remaining URLs indicator ----
    excluded_url_count = total_url_count - len(all_urls)
    render_summary_box(
        f"<strong style='color:#FFFFFF;'>{len(all_urls):,}</strong> URLs remaining "
        f"out of {total_url_count:,} "
        f"(<strong>{excluded_url_count:,}</strong> excluded)"
    )

    # ---- URL browser with selectable rows ----
    with st.expander(f"Browse & select URLs to exclude ({len(all_urls):,} URLs)"):
        st.markdown(
            "<p style='color:#94A3B8;font-size:13px;margin-bottom:8px;'>"
            "Search and check URLs you want to exclude. "
            "Select as many as you need, then click <strong style='color:#F0F4F8;'>Exclude selected</strong>.</p>",
            unsafe_allow_html=True,
        )

        # Search filter
        search_query = st.text_input(
            "Filter URLs",
            placeholder="Type to filter URLs...",
            key="url_browser_search",
            label_visibility="collapsed",
        )

        filtered_urls = all_urls
        if search_query:
            filtered_urls = [u for u in all_urls if search_query.lower() in u.lower()]

        if not filtered_urls:
            st.info("No URLs match your search.")
        else:
            st.markdown(
                f"<p style='color:#64748B;font-size:12px;margin-bottom:4px;'>"
                f"Showing {len(filtered_urls):,} URLs</p>",
                unsafe_allow_html=True,
            )

            browser_df = pd.DataFrame({
                "Exclude": [False] * len(filtered_urls),
                "URL": filtered_urls,
            })

            edited_browser = st.data_editor(
                browser_df,
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config={
                    "Exclude": st.column_config.CheckboxColumn("Exclude", width="small"),
                    "URL": st.column_config.TextColumn("URL", width="large", disabled=True),
                },
                key="url_browser_editor",
            )

            # Apply button — only triggers rerun when user explicitly clicks
            selected = set(edited_browser.loc[edited_browser["Exclude"], "URL"].tolist())
            if selected:
                if st.button(f"Exclude selected ({len(selected):,} URLs)", type="primary"):
                    st.session_state.manual_excluded_urls = manual_excluded | selected
                    st.rerun()

    # ---- Pre-run cost estimate (Phase 11 / A3) -------------------------------
    _render_cost_estimate(len(all_urls))

    # Sticky bottom action bar
    with st._bottom:
        bar_cols = st.columns([1, 3])
        with bar_cols[0]:
            if st.button("← Back to Clean Links", key="step2_back", type="tertiary"):
                st.session_state.wizard_step = "step1"
                st.rerun()
        with bar_cols[1]:
            if st.button("Run Analysis →", key="step2_next", use_container_width=True):
                cleaned = _apply_step2_filters(df, exclude_patterns)
                st.session_state.cleaned_data = cleaned
                st.session_state.exclude_patterns = exclude_patterns
                _start_analysis()


def _start_analysis():
    """Transition to the analyzing screen. Blocks if AI is not available or market is ambiguous."""
    ai_health = st.session_state.get("ai_health")
    if not ai_health or not ai_health.get("ok"):
        error_detail = ai_health.get("error", "Unknown error") if ai_health else "Not checked"
        st.error(
            f"**Cannot run analysis — AI is not connected.**\n\n"
            f"Error: {error_detail}\n\n"
            f"Go back to the top of this page, expand the **AI configuration** panel, "
            f"paste a valid Gemini API key, and click **Connect**."
        )
        return

    # Market gate (linking-rules.md section 5) — block when market is ambiguous
    if not st.session_state.get("market_resolved"):
        from src.analysis.market_detector import detect_market
        cleaned = st.session_state.cleaned_data
        all_urls = pd.unique(pd.concat([cleaned["Source"], cleaned["Destination"]])).tolist()
        detection = detect_market(all_urls)
        st.session_state.market_detection = detection
        if detection["status"] == "resolved":
            st.session_state.market_resolved = detection["market"]
        else:
            # Stop here — user needs to pick a market
            st.warning(
                f"**Market detection is ambiguous** — {detection.get('evidence', '')}\n\n"
                f"Please specify the target market below and click **Confirm market**, "
                f"then click **Run Analysis** again."
            )
            from src.analysis.market_detector import COUNTRY_CODES
            options = ["— Pick a market —"] + sorted(COUNTRY_CODES) + ["multi-market (AI infers per page)"]
            choice = st.selectbox("Market", options, key="market_picker")
            if st.button("Confirm market", key="market_confirm"):
                if choice and not choice.startswith("—"):
                    st.session_state.market_resolved = choice
                    st.rerun()
            return

    st.session_state.wizard_step = "analyzing"
    st.rerun()


# ============================================================
# ANALYZING SCREEN (runs computations with progress)
# ============================================================
def render_analyzing():
    """Run all analysis steps with visible progress, then switch to results."""
    cleaned = st.session_state.cleaned_data
    priority = st.session_state.priority_data

    # Auto-scroll to top on page load
    st.markdown(
        "<script>window.parent.document.querySelector('section.main').scrollTo(0, 0);</script>",
        unsafe_allow_html=True,
    )

    st.markdown("<br><br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<h2 class='analyzing-title'>Analyzing your site</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='text-align:center;color:#94A3B8;font-size:14px;'>"
            f"{len(cleaned):,} links across "
            f"{pd.concat([cleaned['Source'], cleaned['Destination']]).nunique():,} pages</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Progress UI elements
    progress_bar = st.progress(0)
    time_ph = st.empty()
    st.markdown("<br>", unsafe_allow_html=True)
    step1_ph = st.empty()
    step2_ph = st.empty()
    # AI sub-steps: phase label, batch detail, live counters
    step3_phase_ph = st.empty()
    step3_detail_ph = st.empty()
    step3_counts_ph = st.empty()

    start_time = time.time()
    ai_phase_start_time = None  # Track when AI starts for ETA
    analysis_error = None

    def _fmt_time(secs):
        if secs < 60:
            return f"{secs:.0f}s"
        return f"{secs / 60:.1f}min"

    def _step(icon, text, detail=""):
        colors = {"done": "#34D399", "run": "#F0F4F8", "wait": "#64748B"}
        icons = {"done": "\u2705", "run": "\u23F3", "wait": "\u25CB"}
        c = colors.get(icon, "#64748B")
        i = icons.get(icon, "\u25CB")
        pulse = " step-running" if icon == "run" else ""
        elapsed = _fmt_time(time.time() - start_time)
        return (
            f"<p class='{pulse}' style='color:{colors.get(icon, c)};font-size:14px;margin:4px 0;'>"
            f"{i} {text} "
            f"<span style='color:#64748B;font-size:12px;'>{detail}</span></p>"
        )

    def _update_time(eta_text=""):
        elapsed = _fmt_time(time.time() - start_time)
        eta_html = f" &nbsp;|&nbsp; {eta_text}" if eta_text else ""
        time_ph.markdown(
            f"<p style='text-align:center;color:#94A3B8;font-size:13px;"
            f"font-family:\"JetBrains Mono\",monospace;'>"
            f"{elapsed} elapsed{eta_html}</p>",
            unsafe_allow_html=True,
        )

    # Initialize step display
    step1_ph.markdown(_step("run", "Computing link audit..."), unsafe_allow_html=True)
    step2_ph.markdown(_step("wait", "Calculating PageRank"), unsafe_allow_html=True)
    step3_phase_ph.markdown(_step("wait", "AI analysis"), unsafe_allow_html=True)
    _update_time()
    progress_bar.progress(0.05)

    # Step 1: Link audit
    try:
        audit = compute_link_audit(cleaned, full_url_list=st.session_state.full_url_list)
        st.session_state.audit_results = audit
        orphan_summary = f"{audit['all_orphan_count']:,} orphans"
        step1_ph.markdown(
            _step("done", "Link audit", f"\u2014 {audit['total_pages']:,} pages, {orphan_summary}"),
            unsafe_allow_html=True,
        )
    except Exception as e:
        analysis_error = f"Link audit failed: {e}"

    # Step 2: PageRank
    if not analysis_error:
        progress_bar.progress(0.10)
        step2_ph.markdown(_step("run", "Calculating PageRank..."), unsafe_allow_html=True)
        _update_time()
        try:
            scores = compute_pagerank(cleaned)
            st.session_state.pagerank_scores = scores
            _update_time()
            step2_ph.markdown(
                _step("done", "PageRank", f"\u2014 {len(scores):,} pages"),
                unsafe_allow_html=True,
            )
        except Exception as e:
            analysis_error = f"PageRank calculation failed: {e}"

    # Step 3: AI analysis
    if not analysis_error:
        progress_bar.progress(0.15)
        _update_time()

        if GEMINI_API_KEY:
            step3_phase_ph.markdown(
                _step("run", "AI analysis \u2014 connecting to Gemini..."),
                unsafe_allow_html=True,
            )
            step3_detail_ph.markdown(
                "<p style='font-size:12px;color:#64748B;margin:2px 0 2px 28px;'>"
                "First API call may take 15-30 seconds — the AI is thinking.</p>",
                unsafe_allow_html=True,
            )
            _update_time()

            ai_phase_start_time = time.time()
            ai_calls_done = 0  # Track completed API calls for ETA

            def ai_progress(phase, fraction, batch=0, total_batches=0,
                            cocoons_found=0, recs_found=0, total_api_calls=0):
                nonlocal ai_calls_done

                # Update progress bar
                overall = 0.15 + fraction * 0.80
                progress_bar.progress(min(overall, 0.95))

                # Track completed calls for ETA
                if phase == "cocoons":
                    ai_calls_done = batch
                elif phase == "recommendations":
                    # Cocoon batches are done, add rec batches
                    cocoon_batches = total_api_calls - total_batches
                    ai_calls_done = cocoon_batches + batch

                # Calculate ETA
                eta_text = ""
                elapsed_ai = time.time() - ai_phase_start_time
                if ai_calls_done > 0 and total_api_calls > 0:
                    avg_per_call = elapsed_ai / ai_calls_done
                    remaining_calls = total_api_calls - ai_calls_done
                    eta_secs = avg_per_call * remaining_calls
                    if eta_secs > 5:
                        eta_text = f"~{_fmt_time(eta_secs)} remaining"

                _update_time(eta_text)

                # Phase label
                if phase == "preparing":
                    step3_phase_ph.markdown(
                        _step("run", "AI analysis \u2014 preparing page data..."),
                        unsafe_allow_html=True,
                    )
                elif phase == "cocoons":
                    step3_phase_ph.markdown(
                        _step("run", f"AI analysis \u2014 detecting cocoons (batch {batch}/{total_batches})"),
                        unsafe_allow_html=True,
                    )
                elif phase == "recommendations":
                    step3_phase_ph.markdown(
                        _step("run", f"AI analysis \u2014 finding links (batch {batch}/{total_batches})"),
                        unsafe_allow_html=True,
                    )

                # Batch detail: visual sub-progress
                if total_batches > 0 and phase in ("cocoons", "recommendations"):
                    filled = batch
                    empty = total_batches - batch
                    bar = "\u2588" * filled + "\u2591" * empty
                    step3_detail_ph.markdown(
                        f"<p style='font-family:JetBrains Mono,monospace;font-size:13px;color:#64748B;"
                        f"margin:2px 0 2px 28px;'>"
                        f"{bar} &nbsp; {batch}/{total_batches} batches</p>",
                        unsafe_allow_html=True,
                    )

                # Live counters
                step3_counts_ph.markdown(
                    f"<p style='font-size:13px;margin:2px 0 2px 28px;'>"
                    f"<span style='color:#34D399;font-weight:600;'>"
                    f"{cocoons_found}</span>"
                    f"<span style='color:#64748B;'> cocoons found &nbsp;&nbsp; </span>"
                    f"<span style='color:#0EA5E9;font-weight:600;'>"
                    f"{recs_found}</span>"
                    f"<span style='color:#64748B;'> recommendations found</span></p>",
                    unsafe_allow_html=True,
                )

            try:
                # Pass true orphan URLs so the AI can suggest links to/from them
                true_orphans = set(audit.get("true_orphan_pages", []))
                ai_results = run_ai_analysis(
                    cleaned, priority, scores, progress_callback=ai_progress,
                    true_orphan_urls=true_orphans if true_orphans else None,
                )
                st.session_state.ai_results = ai_results
                st.session_state.token_usage = ai_results.get("token_usage")

                n_cocoons = len(ai_results.get("cocoons", []))
                n_recs = len(ai_results.get("recommendations", []))

                if ai_results.get("error") and ai_results["error"] != "no_api_key":
                    step3_phase_ph.markdown(
                        _step("done", "AI analysis", f"\u2014 partial ({ai_results['error']})"),
                        unsafe_allow_html=True,
                    )
                else:
                    step3_phase_ph.markdown(
                        _step("done", "AI analysis", f"\u2014 {n_cocoons} cocoons, {n_recs} recommendations"),
                        unsafe_allow_html=True,
                    )
                # Clear sub-progress now that it's done
                step3_detail_ph.empty()
                step3_counts_ph.empty()

                if ai_results.get("cocoons"):
                    cocoon_health = analyze_cocoon_health(ai_results["cocoons"], cleaned)
                    st.session_state.cocoon_health_data = cocoon_health
            except Exception as e:
                step3_phase_ph.markdown(
                    _step("done", "AI analysis", f"\u2014 failed ({e})"),
                    unsafe_allow_html=True,
                )
                step3_detail_ph.empty()
                step3_counts_ph.empty()
                st.session_state.ai_results = {
                    "cocoons": [],
                    "recommendations": [],
                    "error": f"API error: {e}",
                }
                st.session_state.token_usage = get_token_usage()
        else:
            step3_phase_ph.markdown(
                _step("done", "AI analysis", "\u2014 skipped (no API key)"),
                unsafe_allow_html=True,
            )
            st.session_state.ai_results = {
                "cocoons": [],
                "recommendations": [],
                "error": "no_api_key",
            }

    # Final state
    if not analysis_error:
        progress_bar.progress(1.0)
        time_ph.markdown(
            f"<p style='text-align:center;color:#34D399;font-size:13px;font-weight:600;'>"
            f"\u2705 Complete \u2014 {_fmt_time(time.time() - start_time)}</p>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
        st.session_state.wizard_step = "results"
        st.rerun()
    else:
        time_ph.markdown(
            f"<p style='text-align:center;color:#F87171;font-size:13px;'>"
            f"\u274C Failed \u2014 {_fmt_time(time.time() - start_time)}</p>",
            unsafe_allow_html=True,
        )
        st.error(f"Analysis could not complete: {analysis_error}")
        if st.button("Try Again", use_container_width=True):
            st.session_state.wizard_step = "step2"
            st.rerun()


# ============================================================
# SCREEN 3: RESULTS
# ============================================================
def render_results():
    """Render the full results screen — replaces setup entirely."""
    # Auto-scroll to top
    st.markdown(
        "<script>window.parent.document.querySelector('section.main').scrollTo(0, 0);</script>",
        unsafe_allow_html=True,
    )

    audit = st.session_state.audit_results
    scores = st.session_state.pagerank_scores
    cleaned = st.session_state.cleaned_data
    priority = st.session_state.priority_data

    # Results header with "New Analysis" button
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown("## Analysis Results")
    with col_btn:
        if st.button("New Analysis", use_container_width=True):
            reset_analysis()
            st.rerun()

    st.markdown(
        f"<p style='color:#94A3B8;font-size:14px;margin-bottom:24px;'>"
        f"Based on <strong style='color:#FFFFFF;'>{audit['total_links']:,}</strong> cleaned links "
        f"across <strong style='color:#FFFFFF;'>{audit['total_pages']:,}</strong> pages.</p>",
        unsafe_allow_html=True,
    )

    # ---- Overview stat cards ----
    st.markdown(f"### Overview {render_badge('Audit')}", unsafe_allow_html=True)

    all_orphan_count = audit.get("all_orphan_count", audit.get("orphan_count", 0))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(render_stat_card(f"{audit['total_pages']:,}", "Total Pages"), unsafe_allow_html=True)
    with c2:
        st.markdown(render_stat_card(f"{audit['total_links']:,}", "Internal Links"), unsafe_allow_html=True)
    with c3:
        st.markdown(
            render_stat_card(f"{all_orphan_count:,}", "Orphan Pages", danger=all_orphan_count > 0),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(render_stat_card(f"{audit['inbound_avg']}", "Avg Inbound Links", accent=True), unsafe_allow_html=True)

    # ---- Link distribution details ----
    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("Link distribution details"):
        det1, det2 = st.columns(2)
        with det1:
            st.markdown("**Inbound links per page**")
            st.markdown(
                f"- Average: **{audit['inbound_avg']}**\n"
                f"- Median: **{audit['inbound_median']}**\n"
                f"- Min: **{audit['inbound_min']}** / Max: **{audit['inbound_max']}**"
            )
        with det2:
            st.markdown("**Outbound links per page**")
            st.markdown(
                f"- Average: **{audit['outbound_avg']}**\n"
                f"- Median: **{audit['outbound_median']}**\n"
                f"- Min: **{audit['outbound_min']}** / Max: **{audit['outbound_max']}**"
            )

    # ---- Orphan pages (merged: in-crawl orphans + true orphans from URL list) ----
    if all_orphan_count > 0:
        not_in_crawl = audit.get("true_orphan_count", 0)
        with st.expander(
            f"Orphan pages ({all_orphan_count}) — pages with zero inbound internal links",
            expanded=not_in_crawl > 0,
        ):
            st.markdown(
                "<p style='color:#94A3B8;font-size:13px;margin-bottom:12px;'>"
                "These pages receive zero content links from other pages on your site. "
                "Search engines may struggle to find and rank them. "
                "Every orphan must get at least one inbound link."
                + (
                    f" <strong style='color:#F87171;'>{not_in_crawl:,}</strong> of them aren't in the crawl at all "
                    "(flagged <em>Not in crawl</em> below) — these are the most critical to fix."
                    if not_in_crawl > 0
                    else ""
                )
                + "</p>",
                unsafe_allow_html=True,
            )
            orphan_rows = audit.get("all_orphan_pages") or [
                {"url": u, "in_crawl": True} for u in audit.get("orphan_pages", [])
            ]
            orphan_df = pd.DataFrame(
                [
                    {"URL": r["url"], "Status": "In crawl" if r["in_crawl"] else "Not in crawl"}
                    for r in orphan_rows
                ]
            )
            st.dataframe(orphan_df, use_container_width=True, hide_index=True, height=300)

            # Copy-to-clipboard button — plain URL list
            url_text = "\n".join(r["url"] for r in orphan_rows)
            st.code(url_text, language=None)
            st.caption("Click the copy icon on the top-right of the box to copy the full orphan list.")

    # ---- PageRank distribution ----
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"### PageRank Distribution {render_badge('PageRank')}", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#94A3B8;font-size:14px;margin-bottom:16px;'>"
        "How internal link equity is distributed across the site. "
        "A steep curve means a few pages concentrate most of the authority.</p>",
        unsafe_allow_html=True,
    )

    pr_dist = get_pagerank_distribution(scores)

    fig = px.histogram(
        pr_dist,
        x="PageRank",
        nbins=50,
        color_discrete_sequence=["#0EA5E9"],
        labels={"PageRank": "PageRank Score", "count": "Number of Pages"},
    )
    fig.update_layout(
        xaxis_title="PageRank Score",
        yaxis_title="Number of Pages",
        bargap=0.05,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", size=13, color="#94A3B8"),
        margin=dict(t=10, b=40, l=50, r=20),
        height=350,
    )
    fig.update_xaxes(gridcolor="rgba(37, 64, 85, 0.4)", zerolinecolor="rgba(37, 64, 85, 0.4)")
    fig.update_yaxes(gridcolor="rgba(37, 64, 85, 0.4)", zerolinecolor="rgba(37, 64, 85, 0.4)")
    st.plotly_chart(fig, use_container_width=True)

    # ---- Top pages by PageRank ----
    st.markdown(f"### Top Pages by PageRank {render_badge('PageRank')}", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#94A3B8;font-size:14px;margin-bottom:16px;'>"
        "Pages with the most internal link equity. These are your strongest pages for passing authority.</p>",
        unsafe_allow_html=True,
    )

    top_pages = get_top_pages(scores, n=30)
    # Format PageRank as a more readable number
    top_pages["PageRank"] = top_pages["PageRank"].apply(lambda x: f"{x:.6f}")

    st.dataframe(
        top_pages,
        use_container_width=True,
        hide_index=True,
        height=400,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", width="small"),
            "URL": st.column_config.TextColumn("URL", width="large"),
            "PageRank": st.column_config.TextColumn("PageRank Score", width="medium"),
        },
    )

    # ---- Priority URLs Health ----
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"### Priority URLs Health {render_badge('Audit')}", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:#94A3B8;font-size:14px;margin-bottom:8px;'>"
        f"How well your priority pages are supported by internal links.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='color:#94A3B8;font-size:13px;margin-bottom:4px;'>"
        f"🔴 <strong style='color:#F87171;'>Critical</strong> (0-{HEALTH_CRITICAL_MAX} inbound links) — "
        f"These pages are almost invisible to search engines. They need internal links urgently.</p>"
        f"<p style='color:#94A3B8;font-size:13px;margin-bottom:4px;'>"
        f"🟡 <strong style='color:#FBBF24;'>Warning</strong> ({HEALTH_CRITICAL_MAX+1}-{HEALTH_WARNING_MAX} links) — "
        f"Some support, but not enough for competitive keywords. Add more internal links.</p>"
        f"<p style='color:#94A3B8;font-size:13px;margin-bottom:4px;'>"
        f"🟢 <strong style='color:#34D399;'>Good</strong> ({HEALTH_WARNING_MAX+1}+ links) — "
        f"Well supported. No immediate action needed.</p>"
        f"<p style='color:#94A3B8;font-size:13px;margin-bottom:16px;'>"
        f"<strong style='color:#FFFFFF;'>PageRank</strong> = how much link equity (authority) this page has. "
        f"Higher is better. Compare pages against each other — the exact number matters less than the relative ranking.</p>",
        unsafe_allow_html=True,
    )

    health_df = get_priority_urls_health(
        cleaned,
        priority,
        pagerank_scores=scores,
        critical_max=HEALTH_CRITICAL_MAX,
        warning_max=HEALTH_WARNING_MAX,
    )

    # Health summary counts
    n_critical = (health_df["Health"] == "critical").sum()
    n_warning = (health_df["Health"] == "warning").sum()
    n_good = (health_df["Health"] == "good").sum()

    hc1, hc2, hc3 = st.columns(3)
    with hc1:
        st.markdown(render_health_card(n_critical, "Critical", "critical"), unsafe_allow_html=True)
    with hc2:
        st.markdown(render_health_card(n_warning, "Warning", "warning"), unsafe_allow_html=True)
    with hc3:
        st.markdown(render_health_card(n_good, "Good", "good"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Format PageRank for display
    display_health = health_df.copy()
    if "PageRank" in display_health.columns:
        display_health["PageRank"] = display_health["PageRank"].apply(lambda x: f"{x:.6f}")

    # Health indicator as colored dot
    health_icons = {"critical": "🔴", "warning": "🟡", "good": "🟢"}
    display_health["Status"] = display_health["Health"].map(health_icons)
    display_cols = ["Status", "URL", "Target Keyword", "Inbound Links"]
    if "PageRank" in display_health.columns:
        display_cols.append("PageRank")
    if (display_health["Content Type"] != "").any():
        display_cols.insert(3, "Content Type")

    st.dataframe(
        display_health[display_cols],
        use_container_width=True,
        hide_index=True,
        height=min(400, 40 + len(display_health) * 35),
        column_config={
            "Status": st.column_config.TextColumn("", width="small"),
            "URL": st.column_config.TextColumn("URL", width="large"),
            "Target Keyword": st.column_config.TextColumn("Target Keyword", width="medium"),
            "Inbound Links": st.column_config.NumberColumn("Inbound Links", width="small"),
            "PageRank": st.column_config.TextColumn("PageRank", width="small"),
            "Content Type": st.column_config.TextColumn("Type", width="small"),
        },
    )

    # ---- Cocoon Health ----
    ai_results = st.session_state.ai_results
    cocoon_health = st.session_state.cocoon_health_data

    if ai_results and ai_results.get("error") == "no_api_key":
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        st.warning(
            "**AI features disabled** — No API key configured.\n\n"
            "To enable cocoon detection, link recommendations, and anchor text suggestions, "
            "click **New Analysis**, expand the **AI configuration** panel at the top, "
            "paste your Gemini API key, and re-run."
        )
    else:
        # AI ran — show results (may be partial if some batches failed)
        has_ai_content = False

        # Show error banner if there was a partial or full failure
        ai_error = ai_results.get("error") if ai_results else None
        if ai_error:
            st.markdown("<br>", unsafe_allow_html=True)
            st.warning(f"**AI analysis issue**: {ai_error}")

        # Cocoon health table
        if cocoon_health is not None and not cocoon_health.empty:
            has_ai_content = True
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"### Cocoon Health {render_badge('AI')}",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<p style='color:#94A3B8;font-size:14px;margin-bottom:16px;'>"
                "Operator-based silos detected by AI. Each cocoon groups pages about the same operator "
                "(review, code page, app, guides). The code page should receive links from all siblings.</p>",
                unsafe_allow_html=True,
            )

            # Health summary
            n_poor = (cocoon_health["Health"] == "poor").sum()
            n_weak = (cocoon_health["Health"] == "weak").sum()
            n_good = (cocoon_health["Health"] == "good").sum()

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.markdown(render_health_card(n_poor, "Poor", "critical"), unsafe_allow_html=True)
            with cc2:
                st.markdown(render_health_card(n_weak, "Weak", "warning"), unsafe_allow_html=True)
            with cc3:
                st.markdown(render_health_card(n_good, "Good", "good"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Cocoon table
            health_icons = {"poor": "🔴", "weak": "🟡", "good": "🟢"}
            display_cocoons = cocoon_health.copy()
            display_cocoons["Status"] = display_cocoons["Health"].map(health_icons)
            display_cocoons["Intra-links"] = (
                display_cocoons["Intra-links"].astype(str)
                + " / "
                + display_cocoons["Max Possible"].astype(str)
            )
            display_cocoons["Code Page"] = display_cocoons["Code Page Links"].astype(str) + " →"

            st.dataframe(
                display_cocoons[["Status", "Operator", "Pages", "Intra-links", "Completeness", "Code Page", "Health"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn("", width="small"),
                    "Operator": st.column_config.TextColumn("Operator", width="medium"),
                    "Pages": st.column_config.NumberColumn("Pages", width="small"),
                    "Intra-links": st.column_config.TextColumn("Intra-links", width="small"),
                    "Completeness": st.column_config.NumberColumn("Completeness %", format="%.1f%%", width="small"),
                    "Code Page": st.column_config.TextColumn("Code Page Links", width="small"),
                    "Health": st.column_config.TextColumn("Health", width="small"),
                },
            )

            st.markdown(
                "<p style='color:#64748B;font-size:12px;margin-top:4px;'>"
                "Intra-links: existing / max possible within silo. "
                "Code Page Links: inbound links to the code page from sibling pages.</p>",
                unsafe_allow_html=True,
            )

        # AI Recommendations
        recommendations = ai_results.get("recommendations", []) if ai_results else []

        if recommendations:
            has_ai_content = True
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"### AI Link Recommendations {render_badge('AI')}",
                unsafe_allow_html=True,
            )

            n_high = sum(1 for r in recommendations if r.get("priority") == "high")
            n_med = sum(1 for r in recommendations if r.get("priority") == "medium")
            n_low = sum(1 for r in recommendations if r.get("priority") == "low")

            st.markdown(
                f"<p style='color:#94A3B8;font-size:14px;margin-bottom:16px;'>"
                f"Found <strong style='color:#FFFFFF;'>{len(recommendations)}</strong> opportunities: "
                f"<span style='color:#F87171;font-weight:600;'>{n_high} high</span>, "
                f"<span style='color:#FBBF24;font-weight:600;'>{n_med} medium</span>, "
                f"<span style='color:#34D399;font-weight:600;'>{n_low} low</span> priority.</p>",
                unsafe_allow_html=True,
            )

            # Priority filter
            filter_priority = st.selectbox(
                "Filter by priority",
                ["All", "High", "Medium", "Low"],
                label_visibility="collapsed",
            )

            filtered_recs = recommendations
            if filter_priority != "All":
                filtered_recs = [
                    r for r in recommendations
                    if r.get("priority", "").lower() == filter_priority.lower()
                ]

            # Build orphan + priority lookup so we can tag targets
            orphan_set = set(audit.get("orphan_pages", [])) | set(audit.get("true_orphan_pages", []))
            priority_set = set(st.session_state.priority_data["URL"].tolist()) if st.session_state.priority_data is not None else set()

            def _target_status(target_url: str, is_fallback: bool) -> str:
                if is_fallback:
                    return "Fallback"
                if target_url in orphan_set:
                    return "Orphan"
                if target_url in priority_set:
                    return "Priority"
                return "Standard"

            def _tagged_reason(rec: dict, status: str) -> str:
                base = rec.get("reason", "")
                # Don't double-tag if AI already prefixed it
                if base.startswith("[Orphan target]") or base.startswith("[Priority target]") or base.startswith("[Fallback link]"):
                    return base
                if status == "Orphan":
                    return f"[Orphan target] {base}".strip()
                if status == "Priority":
                    return f"[Priority target] {base}".strip()
                if status == "Fallback":
                    return f"[Fallback link] {base}".strip()
                return base

            # Build recommendations dataframe
            recs_rows = []
            for rec in filtered_recs:
                priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                status = _target_status(rec.get("target_url", ""), bool(rec.get("is_fallback")))
                recs_rows.append({
                    "Priority": priority_icons.get(rec.get("priority", ""), ""),
                    "Source URL": rec.get("source_url", ""),
                    "Target URL": rec.get("target_url", ""),
                    "Anchor": rec.get("suggested_anchor", ""),
                    "Status": status,
                    "Score": int(rec.get("relevance_score", 0)),
                    "Reason": _tagged_reason(rec, status),
                })

            recs_df = pd.DataFrame(recs_rows)

            if not recs_df.empty:
                st.dataframe(
                    recs_df,
                    use_container_width=True,
                    hide_index=True,
                    height=min(600, 40 + len(recs_df) * 35),
                    column_config={
                        "Priority": st.column_config.TextColumn("", width="small"),
                        "Source URL": st.column_config.LinkColumn(
                            "Source URL", width="medium", display_text=r"https?://[^/]+(/.+)?",
                        ),
                        "Target URL": st.column_config.LinkColumn(
                            "Target URL", width="medium", display_text=r"https?://[^/]+(/.+)?",
                        ),
                        "Anchor": st.column_config.TextColumn("Anchor", width="medium"),
                        "Status": st.column_config.TextColumn("Target", width="small"),
                        "Score": st.column_config.NumberColumn("Score", width="small", format="%d"),
                        "Reason": st.column_config.TextColumn("Reason", width="large"),
                    },
                )

        # Fallback: AI ran but produced no results
        if not has_ai_content:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"### AI Analysis {render_badge('AI')}", unsafe_allow_html=True)
            st.info(
                "AI analysis completed but found no cocoons or link recommendations. "
                "This can happen if the API returned empty results or all batches failed silently. "
                "Check the token usage below — if API calls were made, the responses may have been invalid."
            )

    # ---- Token Usage (inline) ----
    token_usage = st.session_state.token_usage
    if token_usage and token_usage.get("api_calls", 0) > 0:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"### AI Token Usage {render_badge('AI')}", unsafe_allow_html=True)
        tc1, tc2, tc3, tc4 = st.columns(4)
        with tc1:
            st.metric("API Calls", f"{token_usage['api_calls']}")
        with tc2:
            st.metric("Input Tokens", f"{token_usage['prompt_tokens']:,}")
        with tc3:
            st.metric("Output Tokens", f"{token_usage['completion_tokens']:,}")
        with tc4:
            st.metric("Thinking Tokens", f"{token_usage['thinking_tokens']:,}")

        total = token_usage["total_tokens"]
        st.markdown(
            f"<p style='color:#64748B;font-size:12px;margin-top:8px;'>"
            f"Total: {total:,} tokens. "
            f"Estimated cost: ~${(token_usage['prompt_tokens'] * 0.10 + token_usage['completion_tokens'] * 0.40) / 1_000_000:.4f} "
            f"(free tier: 20 req/day, 1M tokens/day)</p>",
            unsafe_allow_html=True,
        )

    # ---- Downloads (rendered in sticky st._bottom below) ----
    recommendations = ai_results.get("recommendations", []) if ai_results else []

    csv_orphans = set(audit.get("orphan_pages", [])) | set(audit.get("true_orphan_pages", []))
    csv_priorities = (
        set(st.session_state.priority_data["URL"].tolist())
        if st.session_state.priority_data is not None
        else set()
    )
    csv_content = generate_linking_plan_csv(
        cleaned_df=cleaned,
        recommendations=recommendations,
        orphan_urls=csv_orphans,
        priority_urls=csv_priorities,
    )

    # Side-by-side downloads: CSV + HTML report
    from datetime import datetime as _dt
    from src.export.html_report import generate_html_report
    from src.parsers.screaming_frog import get_primary_domain

    site_domain = get_primary_domain(cleaned)
    date_slug = _dt.now().strftime("%Y-%m-%d")
    base_name = f"{site_domain.replace('.', '-')}-{date_slug}"

    health_df = get_priority_urls_health(
        cleaned, st.session_state.priority_data, pagerank_scores=scores,
        critical_max=HEALTH_CRITICAL_MAX, warning_max=HEALTH_WARNING_MAX,
    ) if st.session_state.priority_data is not None else None

    html_content = generate_html_report(
        site_domain=site_domain,
        audit=audit,
        pagerank_scores=scores,
        priority_health_df=health_df if health_df is not None else pd.DataFrame(columns=["URL", "Target Keyword", "Content Type", "Inbound Links", "Health", "PageRank"]),
        cocoon_health_df=st.session_state.get("cocoon_health_data"),
        recommendations=recommendations,
        token_usage=st.session_state.get("token_usage"),
    )

    with st._bottom:
        dl_csv, dl_html = st.columns(2)
        with dl_csv:
            st.download_button(
                label="Download Linking Plan (CSV)",
                data=csv_content,
                file_name=f"{base_name}-linking-plan.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl_html:
            st.download_button(
                label="Download Full Report (HTML)",
                data=html_content,
                file_name=f"{base_name}-report.html",
                mime="text/html",
                use_container_width=True,
            )


# ============================================================
# MAIN ROUTING — 3 screens
# ============================================================
def main():
    """Main app routing: Login → Setup → Analyzing → Results."""

    # Screen 1: Login
    if not st.session_state.authenticated:
        render_header()
        render_login()
        return

    # Run AI health check once after login
    if st.session_state.ai_health is None:
        st.session_state.ai_health = check_api_health()

    # Analyzing screen (transition between setup and results)
    if st.session_state.wizard_step == "analyzing":
        render_header()
        render_analyzing()
        return

    # Screen 3: Results (no step indicator — different layout)
    if st.session_state.wizard_step == "results":
        render_header()
        render_results()
        return

    # Screen 2: Setup (step indicator + wizard)
    render_header()

    # AI configuration — API key + health check
    ai_health = st.session_state.ai_health
    with st.expander(
        "AI connected — Gemini API is ready." if (ai_health and ai_health["ok"])
        else "AI unavailable — click to configure" if (ai_health and not ai_health["ok"])
        else "AI configuration",
        expanded=not (ai_health and ai_health["ok"]),
        icon=":material/check_circle:" if (ai_health and ai_health["ok"]) else ":material/error:",
    ):
        # Dev mode shows the model picker for A/B testing; production hides it.
        if src.config.ILA_DEV_MODE:
            key_col, model_col, btn_col = st.columns([2, 1.2, 1])
        else:
            key_col, btn_col = st.columns([3, 1])
            model_col = None
        with key_col:
            api_key_input = st.text_input(
                "Gemini API Key",
                type="password",
                placeholder="Paste your Gemini API key (optional — uses default if empty)",
                label_visibility="collapsed",
            )
        model_input = ""
        if model_col is not None:
            with model_col:
                current_model = os.environ.get("GEMINI_MODEL", src.config.GEMINI_MODEL)
                model_input = st.text_input(
                    "Model ID",
                    value=current_model,
                    placeholder="gemini-3.1-flash-lite-preview",
                    label_visibility="collapsed",
                    help="Dev only — override the Gemini model ID. Default is Flash-Lite Preview (cheap). Opt-in upgrades: gemini-3-flash-preview (more capable), gemini-3.1-pro-preview (premium, expensive). Verify IDs with Google's docs before swapping.",
                )
        with btn_col:
            if st.button("Connect", use_container_width=True):
                if api_key_input and api_key_input.strip():
                    st.session_state.user_api_key = api_key_input.strip()
                    os.environ["GEMINI_API_KEY"] = api_key_input.strip()
                if model_input and model_input.strip():
                    os.environ["GEMINI_MODEL"] = model_input.strip()
                importlib.reload(src.config)
                # Re-run health check with new key
                st.session_state.ai_health = check_api_health()
                st.rerun()

        # Status + disconnect control — never reveals the key itself.
        if ai_health and ai_health.get("ok"):
            if st.session_state.get("user_api_key"):
                source = "your session (cleared on Disconnect)"
            elif st.secrets.get("GEMINI_API_KEY", None):
                source = "Streamlit secrets"
            elif os.environ.get("GEMINI_API_KEY"):
                source = "environment variable"
            else:
                source = "default"
            st.caption(f"Key source: {source}. The key is never displayed or logged.")
            if st.button("Disconnect / clear key", key="disconnect_api", type="tertiary"):
                st.session_state.user_api_key = None
                if "GEMINI_API_KEY" in os.environ:
                    del os.environ["GEMINI_API_KEY"]
                importlib.reload(src.config)
                st.session_state.ai_health = check_api_health()
                st.rerun()

        if ai_health and not ai_health["ok"]:
            st.markdown(
                f"<p style='color:#F87171;font-size:13px;margin-top:4px;'>"
                f"Error: {ai_health['error']}</p>",
                unsafe_allow_html=True,
            )

    render_setup_step_indicator()

    step = st.session_state.wizard_step
    if step == "upload":
        render_upload()
    elif step == "step1":
        render_cleaning_step1()
    elif step == "step2":
        render_cleaning_step2()


if __name__ == "__main__":
    main()
