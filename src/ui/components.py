"""Reusable UI components — Nordic Precision design system.

Distinctive dark interface inspired by Better Collective's Nordic roots.
Signature: teal-to-emerald gradient accent representing link equity flow.
"""

import streamlit as st


# ===== Design Tokens =====
COLORS = {
    "bg_primary": "#0B1621",
    "bg_elevated": "#0F1D2B",
    "bg_card": "rgba(15, 29, 43, 0.7)",
    "bg_card_solid": "#122232",
    "bg_input": "#080F18",
    "border_subtle": "rgba(37, 64, 85, 0.6)",
    "border_glow": "rgba(0, 168, 104, 0.25)",
    "text_primary": "#F0F4F8",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    "accent": "#00A868",
    "accent_light": "#34D399",
    "accent_bright": "#00D68F",
    "success": "#34D399",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "orange": "#FB923C",
    "cta": "#0EA5E9",
    "cta_hover": "#38BDF8",
    "score_green": "#34D399",
    "score_yellow": "#FBBF24",
    "score_orange": "#FB923C",
    "score_red": "#F87171",
}


def apply_bc_theme():
    """Apply Nordic Precision dark theme — distinctive BC brand experience."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700;800;900&display=swap');

        :root {
            --bg-primary: #0B1621;
            --bg-elevated: #0F1D2B;
            --bg-card: rgba(15, 29, 43, 0.7);
            --bg-input: #080F18;
            --border: rgba(37, 64, 85, 0.6);
            --border-glow: rgba(0, 168, 104, 0.25);
            --text-1: #F0F4F8;
            --text-2: #94A3B8;
            --text-3: #64748B;
            --accent: #00A868;
            --accent-light: #34D399;
            --accent-bright: #00D68F;
            --cta: #0EA5E9;
            --cta-hover: #38BDF8;
            --danger: #F87171;
            --warning: #FBBF24;
            --gradient-brand: linear-gradient(135deg, #005947, #00A868, #00D68F);
            --gradient-brand-h: linear-gradient(90deg, #005947, #00A868, #00D68F);
            --glass: rgba(15, 29, 43, 0.55);
            --glass-border: rgba(37, 64, 85, 0.45);
        }

        /* ---- Fonts ---- */
        html, body, [class*="css"] {
            font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            -webkit-font-smoothing: antialiased;
        }

        /* ---- Background: gradient wash for depth ---- */
        .stApp {
            background: var(--bg-primary);
            background-image:
                radial-gradient(ellipse 80% 60% at 10% 0%, rgba(0, 89, 71, 0.12) 0%, transparent 60%),
                radial-gradient(ellipse 60% 50% at 90% 100%, rgba(0, 168, 104, 0.06) 0%, transparent 50%);
        }
        .main .block-container {
            background: transparent;
            padding-top: 0 !important;
            overflow-x: hidden;
        }
        section[data-testid="stSidebar"] {
            background: var(--bg-elevated);
        }

        /* ---- Text ---- */
        .stApp, .stApp p, .stApp span, .stApp label, .stApp div {
            color: var(--text-1);
        }
        .stApp .stMarkdown p {
            color: var(--text-1);
        }

        /* ---- Streamlit chrome ---- */
        .stApp > header { display: none; }
        .stMainBlockContainer { padding-top: 0 !important; }
        [data-testid="stAppViewBlockContainer"] { padding-top: 0 !important; }
        #MainMenu { visibility: hidden; }
        .stApp > footer { visibility: hidden; }
        header[data-testid="stHeader"] { visibility: hidden; }

        /* ===== HEADER ===== */
        .bc-header {
            background: var(--bg-elevated);
            padding: 18px 32px 14px 32px;
            margin: -6rem -4rem 0 -4rem;
            position: relative;
            overflow: hidden;
        }
        /* Signature animated gradient accent line */
        .bc-header::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--gradient-brand-h);
            background-size: 200% 100%;
            animation: gradientSlide 4s ease-in-out infinite;
        }
        @keyframes gradientSlide {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .bc-header-inner {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .bc-header-brand {
            color: var(--text-1);
            font-family: 'Outfit', sans-serif;
            font-size: 17px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 14px;
            letter-spacing: -0.3px;
        }
        .bc-header-brand .bc-logo {
            background: var(--gradient-brand);
            border-radius: 8px;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 800;
            color: #FFFFFF;
            font-family: 'Outfit', sans-serif;
            letter-spacing: 0.5px;
        }
        .bc-header-sub {
            color: var(--text-3);
            font-size: 13px;
            font-weight: 400;
            letter-spacing: 0.5px;
        }
        .bc-header-spacer {
            margin-bottom: 2rem;
        }

        /* ===== BUTTONS ===== */
        .stButton > button {
            background: linear-gradient(135deg, #0C8EBF, #0EA5E9);
            color: #FFFFFF;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            font-family: 'DM Sans', sans-serif;
            letter-spacing: 0.2px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, #0EA5E9, #38BDF8);
            color: #FFFFFF;
            border: none;
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(14, 165, 233, 0.3);
        }
        .stButton > button:active {
            transform: translateY(0);
        }

        /* Download button — green gradient */
        .stDownloadButton > button {
            background: linear-gradient(135deg, #005947, #00A868);
            color: #FFFFFF;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            font-family: 'DM Sans', sans-serif;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 8px rgba(0, 168, 104, 0.15);
        }
        .stDownloadButton > button:hover {
            background: linear-gradient(135deg, #00A868, #34D399);
            color: #FFFFFF;
            box-shadow: 0 4px 16px rgba(0, 168, 104, 0.3);
            transform: translateY(-1px);
        }

        /* ===== BADGES ===== */
        .bc-badge {
            background: rgba(0, 168, 104, 0.1);
            color: #34D399;
            font-size: 10px;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            padding: 3px 10px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: inline-block;
            border: 1px solid rgba(0, 168, 104, 0.15);
        }

        /* ===== STAT CARDS — Glass + monospace numbers ===== */
        .stat-card {
            background: var(--glass);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            padding: 24px 16px;
            text-align: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(0, 168, 104, 0.3), transparent);
            opacity: 0;
            transition: opacity 0.3s;
        }
        .stat-card:hover {
            border-color: var(--border-glow);
            transform: translateY(-2px);
        }
        .stat-card:hover::before {
            opacity: 1;
        }
        .stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 30px;
            font-weight: 700;
            color: var(--text-1);
            line-height: 1.1;
            letter-spacing: -0.5px;
        }
        .stat-value.accent {
            color: var(--accent-light);
            text-shadow: 0 0 20px rgba(0, 168, 104, 0.25);
        }
        .stat-value.danger {
            color: var(--danger);
            text-shadow: 0 0 20px rgba(248, 113, 113, 0.2);
        }
        .stat-label {
            font-family: 'Outfit', sans-serif;
            font-size: 11px;
            color: var(--text-3);
            margin-top: 8px;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            font-weight: 500;
        }

        /* ===== HEALTH CARDS — Glow halos ===== */
        .health-card {
            text-align: center;
            padding: 14px 10px;
            border-radius: 12px;
            border: 1px solid var(--glass-border);
            background: var(--glass);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            transition: all 0.3s;
        }
        .health-card.critical {
            background: rgba(248, 113, 113, 0.06);
            border-color: rgba(248, 113, 113, 0.2);
            box-shadow: 0 0 20px rgba(248, 113, 113, 0.05);
        }
        .health-card.warning {
            background: rgba(251, 191, 36, 0.06);
            border-color: rgba(251, 191, 36, 0.2);
            box-shadow: 0 0 20px rgba(251, 191, 36, 0.05);
        }
        .health-card.good {
            background: rgba(52, 211, 153, 0.06);
            border-color: rgba(52, 211, 153, 0.2);
            box-shadow: 0 0 20px rgba(52, 211, 153, 0.05);
        }
        .health-card .health-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 24px;
            font-weight: 700;
            line-height: 1.2;
        }
        .health-card.critical .health-value { color: #F87171; }
        .health-card.warning .health-value { color: #FBBF24; }
        .health-card.good .health-value { color: #34D399; }
        .health-card .health-label {
            font-family: 'Outfit', sans-serif;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            font-weight: 600;
            margin-top: 4px;
        }
        .health-card.critical .health-label { color: #F87171; }
        .health-card.warning .health-label { color: #FBBF24; }
        .health-card.good .health-label { color: #34D399; }

        /* ===== CONTENT TYPE BADGES ===== */
        .ct-badge {
            font-family: 'Outfit', sans-serif;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }
        .ct-code { background: rgba(248, 113, 113, 0.1); color: #F87171; border: 1px solid rgba(248, 113, 113, 0.15); }
        .ct-comparator { background: rgba(251, 191, 36, 0.1); color: #FBBF24; border: 1px solid rgba(251, 191, 36, 0.15); }
        .ct-guide { background: rgba(52, 211, 153, 0.1); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.15); }
        .ct-review { background: rgba(14, 165, 233, 0.1); color: #0EA5E9; border: 1px solid rgba(14, 165, 233, 0.15); }

        /* Status badges */
        .status-add { background: rgba(52, 211, 153, 0.1); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.15); }
        .status-live { background: rgba(148, 163, 184, 0.1); color: #94A3B8; border: 1px solid rgba(148, 163, 184, 0.1); }
        .status-remove { background: rgba(248, 113, 113, 0.1); color: #F87171; border: 1px solid rgba(248, 113, 113, 0.15); }

        /* ===== UPLOAD CONTAINERS ===== */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--glass);
            border: 1px solid var(--glass-border) !important;
            border-radius: 12px !important;
            transition: border-color 0.3s;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(14, 165, 233, 0.25) !important;
        }

        /* ===== UPLOAD CONFIRMATION ===== */
        .upload-ok {
            background: rgba(52, 211, 153, 0.06);
            border-left: 3px solid #34D399;
            padding: 8px 14px;
            border-radius: 0 8px 8px 0;
            font-size: 12px;
            color: #34D399;
            margin: 4px 0 0 0;
            backdrop-filter: blur(8px);
            font-family: 'JetBrains Mono', monospace;
        }

        /* ===== SUMMARY BOXES ===== */
        .summary-box {
            background: var(--glass);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 16px 20px;
            font-size: 13px;
            color: var(--text-2);
            margin: 16px 0;
        }
        .summary-box strong {
            color: var(--text-1);
        }

        /* ===== FORM INPUTS — dark with glow focus ===== */
        .stFileUploader > div {
            background-color: var(--bg-input);
            border-color: var(--border);
            border-radius: 10px;
        }
        .stFileUploader label {
            color: var(--text-2) !important;
        }

        .stTextInput input {
            background-color: var(--bg-input) !important;
            color: var(--text-1) !important;
            border: 1px solid var(--border) !important;
            border-radius: 10px !important;
            font-family: 'DM Sans', sans-serif !important;
            transition: all 0.3s !important;
        }
        .stTextInput input:focus {
            border-color: rgba(14, 165, 233, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1) !important;
        }
        .stTextInput input::placeholder {
            color: var(--text-3) !important;
        }

        .stSelectbox > div > div {
            background-color: var(--bg-input);
            color: var(--text-1);
            border-color: var(--border);
            border-radius: 10px;
        }

        .stCheckbox label span {
            color: var(--text-1) !important;
        }

        /* Expander */
        .streamlit-expanderHeader {
            background-color: var(--bg-elevated);
            color: var(--text-1);
            border-color: var(--border);
            border-radius: 10px;
        }

        /* Data frame */
        .stDataFrame {
            border-radius: 10px;
            overflow: hidden;
        }

        /* Metrics */
        [data-testid="stMetricValue"] {
            color: var(--text-1);
            font-family: 'JetBrains Mono', monospace;
        }
        [data-testid="stMetricLabel"] {
            color: var(--text-2);
            font-family: 'Outfit', sans-serif;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.8px;
        }

        /* Divider */
        hr {
            border-color: var(--border);
        }

        /* Alerts */
        .stAlert {
            background-color: var(--bg-elevated);
            border-radius: 10px;
        }

        /* ===== PAGE LOAD ANIMATION ===== */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(12px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .stApp .main .block-container > div {
            animation: fadeInUp 0.5s ease-out;
        }

        /* ===== HEADINGS — Outfit font ===== */
        .stApp h1, .stApp h2, .stApp h3 {
            font-family: 'Outfit', sans-serif !important;
            letter-spacing: -0.3px;
        }
        .stApp h2 {
            font-weight: 700;
            font-size: 22px;
        }
        .stApp h3 {
            font-weight: 600;
            font-size: 17px;
        }

        /* ===== PROGRESS BAR — gradient ===== */
        .stProgress > div > div > div {
            background: var(--gradient-brand) !important;
        }

        /* ===== PLOTLY CHART CONTAINER ===== */
        .js-plotly-plot {
            border-radius: 12px;
            overflow: hidden;
        }

        /* ===== LOGIN SCREEN SPECIFICS ===== */
        .login-title {
            text-align: center;
            font-family: 'Outfit', sans-serif;
            font-size: 28px;
            font-weight: 800;
            color: var(--text-1);
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        }
        .login-subtitle {
            text-align: center;
            color: var(--text-3);
            font-size: 14px;
            margin-bottom: 36px;
            line-height: 1.5;
        }
        .login-field-label {
            color: var(--text-2);
            font-family: 'Outfit', sans-serif;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 4px;
        }
        .login-field-hint {
            color: var(--text-3);
            font-size: 11px;
            font-weight: 400;
            text-transform: none;
            letter-spacing: 0;
        }
        .login-divider {
            border-top: 1px solid var(--border);
            margin: 20px 0;
        }

        /* ===== STEP INDICATOR ===== */
        .step-done {
            text-align: center;
            font-weight: 500;
            font-size: 13px;
            font-family: 'Outfit', sans-serif;
        }
        .step-done .step-circle {
            background: #34D399;
            color: #0B1621;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            box-shadow: 0 0 12px rgba(52, 211, 153, 0.3);
        }
        .step-done .step-text { color: #34D399; }

        .step-active {
            text-align: center;
            font-weight: 600;
            font-size: 13px;
            font-family: 'Outfit', sans-serif;
        }
        .step-active .step-circle {
            background: linear-gradient(135deg, #0C8EBF, #0EA5E9);
            color: #FFFFFF;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            box-shadow: 0 0 12px rgba(14, 165, 233, 0.3);
        }
        .step-active .step-text { color: #F0F4F8; }

        .step-future {
            text-align: center;
            font-weight: 500;
            font-size: 13px;
            font-family: 'Outfit', sans-serif;
        }
        .step-future .step-circle {
            background: rgba(15, 29, 43, 0.7);
            color: var(--text-3);
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            border: 1px solid var(--border);
        }
        .step-future .step-text { color: var(--text-3); }

        /* ===== ANALYZING SCREEN ===== */
        .analyzing-title {
            text-align: center;
            font-family: 'Outfit', sans-serif;
            font-size: 24px;
            font-weight: 700;
            color: var(--text-1);
            letter-spacing: -0.3px;
        }
        .analyzing-sub {
            text-align: center;
            color: var(--text-2);
            font-size: 14px;
        }

        /* Pulsing animation for running steps */
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .step-running {
            animation: pulse 1.5s ease-in-out infinite;
        }

        /* URL match indicators */
        .url-match-ok {
            background: rgba(52, 211, 153, 0.06);
            border-left: 3px solid #34D399;
            padding: 10px 16px;
            border-radius: 0 10px 10px 0;
            font-size: 13px;
            color: #34D399;
            margin-bottom: 6px;
        }
        .url-match-warn {
            background: rgba(251, 191, 36, 0.06);
            border-left: 3px solid #FBBF24;
            padding: 10px 16px;
            border-radius: 0 10px 10px 0;
            font-size: 13px;
            color: #FBBF24;
            margin-bottom: 6px;
        }
        .url-match-err {
            background: rgba(248, 113, 113, 0.06);
            border-left: 3px solid #F87171;
            padding: 10px 16px;
            border-radius: 0 10px 10px 0;
            font-size: 13px;
            color: #F87171;
            margin-bottom: 6px;
        }

        /* ===== SECTION HEADING STYLE ===== */
        .section-heading {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            color: var(--text-1);
            letter-spacing: -0.3px;
        }

        /* ===== MONOSPACE DATA ===== */
        .mono-data {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-3);
        }

        /* ===== STICKY ACTION BAR (st._bottom) ===== */
        /* Style the bottom container to match Nordic Precision theme */
        [data-testid="stBottom"] {
            background: rgba(11, 22, 33, 0.92) !important;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-top: 1px solid var(--glass-border);
            box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3);
        }
        [data-testid="stBottomBlockContainer"] {
            padding-top: 12px !important;
            padding-bottom: 12px !important;
        }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    """Render the Better Collective branded header with gradient accent line."""
    st.markdown("""
    <div class="bc-header">
        <div class="bc-header-inner">
            <div class="bc-header-brand">
                <span class="bc-logo">BC</span>
                Internal Link Analyzer
            </div>
            <div class="bc-header-sub">SEO Tools &middot; Better Collective</div>
        </div>
    </div>
    <div class="bc-header-spacer"></div>
    """, unsafe_allow_html=True)


def render_stat_card(value, label, danger=False, accent=False):
    """Render a glass-morphism stat card with monospace numbers."""
    extra_class = ""
    if danger:
        extra_class = " danger"
    elif accent:
        extra_class = " accent"
    return f"""
    <div class="stat-card">
        <div class="stat-value{extra_class}">{value}</div>
        <div class="stat-label">{label}</div>
    </div>
    """


def render_health_card(value, label, level):
    """Render a health status card with glow halo."""
    return f"""
    <div class="health-card {level}">
        <div class="health-value">{value}</div>
        <div class="health-label">{label}</div>
    </div>
    """


def render_upload_confirmation(filename, detail):
    """Render a green upload confirmation bar."""
    st.markdown(
        f'<div class="upload-ok">&#10003; {filename} &mdash; {detail}</div>',
        unsafe_allow_html=True,
    )


def render_badge(text):
    """Render a BC-styled badge."""
    return f'<span class="bc-badge">{text}</span>'


def render_summary_box(html_content):
    """Render a glass summary box with stats."""
    st.markdown(
        f'<div class="summary-box">{html_content}</div>',
        unsafe_allow_html=True,
    )
