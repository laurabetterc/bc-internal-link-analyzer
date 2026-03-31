# Internal Link Analyzer — Project CLAUDE.md

## Quick Links
- **PRD**: `docs/PRD.md` (single source of truth for all specs)
- **Plan**: `docs/plan.md` (tech stack, architecture, wireframes)
- **Roadmap**: `docs/ROADMAP.md` (task checklist)
- **Progress**: `docs/PROGRESS.md` (session journal)
- **APIs**: `docs/APIS.md` (external services & keys)
- **Wireframe**: `docs/wireframe.html` (open in browser to see the UI mockup)

## Current Status
- **PRD**: Approved
- **Plan**: Approved
- **Code**: Phases 1-8 complete. v1 feature-complete + design revamp + UX overhaul + upload redesign.
- **Deployment**: Live at https://bc-inter-linking.streamlit.app/
- **Phase**: Ready for team feedback (Phase 9). Users can paste their own Gemini API key on the Setup screen.
- **GitHub**: Public repo at `laurabetterc/clause-seo-bc` (branch `feat/serp-optimization/project-setup`)

## Tech Stack
- **Framework**: Streamlit (Python) — single-page web app
- **Data processing**: pandas (CSV parsing), networkx (PageRank)
- **Charts**: Plotly
- **AI**: Gemini 2.5 Flash (Google) — semantic analysis, cocoon detection, anchor suggestions (thinking mode enabled)
- **Export**: CSV (linking plan with all links: "live" + "to add")
- **Output**: Web dashboard + CSV download
- **Design**: "Nordic Precision" dark theme (Outfit + DM Sans + JetBrains Mono, glass-morphism cards, teal-to-emerald gradient accents, animated header line)

## Key Commands
```bash
# Activate virtual environment
source venv/bin/activate

# Run the app (without AI features)
streamlit run src/app.py

# Run the app WITH AI features
GEMINI_API_KEY=your-api-key streamlit run src/app.py

# Password: bcseo2026 (or set ILA_PASSWORD env var)
```

## Deployed App
- **URL**: https://bc-inter-linking.streamlit.app/
- **Secrets**: Configured in Streamlit Cloud (GEMINI_API_KEY, ILA_PASSWORD)
- **Branch**: `feat/serp-optimization/project-setup` (auto-deploys on push)
- **API key**: Rotated on 2026-02-24 (old key leaked via git history). New key ONLY in Streamlit Cloud Secrets — never commit keys to files.

## Project Context
- Internal web tool for SEO team (3-5 users)
- Input: Screaming Frog CSV + Priority URLs CSV (URL, Target Keyword, optional Content Type) + optional Full Site URL List (for true orphan detection)
- Key concept: **Cocoons** — operator-based semantic silos where the code page is the main authority target
- No persistent storage — standalone analyses
- Single shared password for access

## GitHub Accounts
- **laurabetterc**: Active account for this project
- **pattmobil**: Available via `gh auth switch -u pattmobil` (for other projects)

## Sample Data
- Real Screaming Frog export: `/Users/lauragaiton/Desktop/Bureau - MacBook Pro de Laura/crawls/all_inlinks_bolavip.csv`
