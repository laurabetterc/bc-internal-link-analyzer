# Roadmap — Internal Link Analyzer

Task checklist. See `plan.md` for architecture details and `PRD.md` for full specs.

---

## Phase 0: Project Setup
- [x] Create project folder structure
- [x] Conduct PRD interview
- [x] Write PRD
- [x] Laura approves PRD
- [x] Create technical plan + wireframes
- [x] Laura approves plan

## Phase 1: Foundation (CSV parsing + cleaning wizard)
- [x] Initialize Streamlit project, install dependencies
- [x] Build main app skeleton (single-page layout, title, sections)
- [x] Build Screaming Frog CSV parser (validate columns, load data)
- [x] Build Priority URLs CSV parser (URL, Target Keyword, optional Content Type)
- [x] Build file upload UI (two side-by-side uploaders with validation feedback)
- [x] Build cleaning Step 1: link position filter (auto-detect positions, show summary table, confirm button)
- [x] Build cleaning Step 2: URL pattern detection (scan paths, group patterns, toggle table, custom pattern input)
- [x] Wire up session state to track wizard progress (upload → step 1 → step 2 → ready)

## Phase 2: Analysis Engine (link audit + PageRank)
- [x] Build link audit: compute total pages, total links, orphan pages, links per page stats
- [x] Build PageRank calculation using networkx (directed graph from cleaned links)
- [x] Build overview stats UI (4 metric cards: pages, links, orphans, avg links/page)
- [x] Build PageRank distribution chart (Plotly histogram)
- [x] Build top pages by PageRank table
- [x] Build Priority URLs health table (moved from Phase 3 — no AI needed)
- [x] Restructure app to 3-screen layout (Login → Setup → Results)

## Phase 3: AI Intelligence (Claude API)
- [x] Set up Anthropic API key configuration (environment variable)
- [x] Build AI batching logic (group pages into batches of ~50, structured context per page)
- [x] Build cocoon detection prompt (AI auto-groups pages by operator from URL slugs/keywords)
- [x] Build intra-cocoon link analysis (existing links within each silo, links pointing to code page)
- [x] Build cocoon health UI (per-operator table: pages, intra-links, code page support, health score)
- [x] Build semantic analysis prompt (find linking opportunities, detect gaps, prioritize cocoon-strengthening links)
- [x] Build anchor text suggestion prompt (combined with semantic analysis for efficiency)
- [x] Build PageRank strategy prompt (combined with semantic analysis — high-PR context included per page)
- [x] Build AI recommendations table (source, target, anchor, reason, priority filter)
- [x] Add progress indicator during AI analysis (st.status with step-by-step updates)
- [x] Graceful fallback when no API key (show audit/PageRank results, warn about AI features)

## Phase 4: Export & Polish
- [x] Build Excel export (Source URL, Anchor, Target URL, Status, Priority, Reason columns)
- [x] Include "live" links + "to add" recommendations in Excel (2 sheets: Linking Plan + Summary)
- [x] Add simple password authentication (done in Phase 1)
- [x] Add error handling (try/except on analysis steps, graceful API failure, "Try Again" button)
- [x] UI polish: 3-screen layout, progress indicator, section badges, health summary cards

## Phase 5: Testing with Real Data
- [x] Switch AI provider from Claude API to Gemini 2.5 Flash (cost savings)
- [x] Add AI token usage tracking (input, output, thinking tokens, cost estimate)
- [x] Add token usage to dashboard UI (expandable section) and Excel Summary sheet
- [x] Add rate limit handling with retry logic (429 errors)
- [x] Test with real Screaming Frog export (44K rows bolavip)
- [x] Verify cleaning wizard correctly filters positions and patterns
- [x] Verify PageRank produces reasonable scores (sum=1.0, top pages are hubs)
- [x] Create realistic priority URLs test file (15 URLs across 4 content types)
- [x] Verify AI recommendations are relevant and anchor texts make sense
- [x] Verify Excel export is complete and correctly formatted (with AI results)
- [x] Performance check: full pipeline in 0.76s without AI, ~536s with AI (over 5 min target — due to Gemini thinking mode)
- [x] Fix cocoon detection: batch URLs, prioritize priority URLs, use full URLs in prompts
- [x] Fix link recommendations: reduce batch size to 20, retest with API quota
- [x] Fix max_output_tokens: 4096 → 16384 (Gemini thinking tokens were truncating JSON output)
- [x] Fix cocoon batch size: 80 → 40 (main operators missed with larger batches)

## Phase 6: Deployment (Streamlit Community Cloud)
- [x] Scrub API keys from PROGRESS.md
- [x] Add `st.secrets` bridge in app.py (Streamlit Cloud reads secrets differently from env vars)
- [x] Add `.streamlit/secrets.toml` to .gitignore
- [x] Create root-level requirements.txt (Streamlit Cloud reads deps from repo root)
- [x] Delete repo created on wrong GitHub account (pattmobil — Laura deleted via browser)
- [x] Log into correct GitHub account (`gh auth login` — laurabetterc)
- [x] Create GitHub repo on correct account (public — Streamlit Cloud needed public access)
- [x] Push code to GitHub (both main + feature branch)
- [x] Align UI design with SERP Optimization dark theme (Inter font, dark backgrounds, new color palette)
- [x] Deploy on Streamlit Community Cloud (connect repo, add secrets, deploy)
- [x] Verify app works on deployed URL — login, upload, cleaning confirmed working
- [x] Re-test full analysis with thinking re-enabled (thinking_budget:0 removed — was breaking AI)
- [x] Rotate leaked Gemini API key (old key in git history, new key in Streamlit Cloud Secrets only)
- [ ] Share URL with team and collect feedback

## Phase 7: UX Improvements (from user testing feedback)
- [x] Step 1: Replace read-only table + separate checkboxes with interactive `st.data_editor`
- [x] Step 2: Add scrollable URL browser to spot missing patterns
- [x] Analysis progress: Replace `st.status` with progress bar, elapsed time, step checkmarks
- [x] Performance: Disable Gemini thinking mode (`thinking_budget: 0`) — later reverted (was breaking AI)
- [x] Add pagination detection and filtering (query params + path patterns)
- [x] Add external link filtering at parse time (auto-detect primary domain)
- [x] Flip pattern UX from "Keep" to "Exclude" (check = exclude)
- [x] Add selectable URLs in browser with Exclude checkboxes
- [x] Replace XLSX export with CSV (all links: "live" + "to add")
- [x] Add priority URL template download button
- [x] Improve Priority URL health readability (explain statuses + PageRank)
- [x] Show token usage inline (remove dropdown)
- [x] Fix AI pipeline: remove thinking_budget:0, per-batch error handling
- [x] Fix AI section disappearing when analysis fails or returns empty
- [x] Add AI health check on login (verify API before full analysis)
- [x] Improve analyzing screen: live result counters, ETA, visual batch progress

## Phase 8: Design Revamp & UX Overhaul (Sessions 11-12)
- [x] Fix AI health check (thinking mode + max_output_tokens too small)
- [x] Add user-provided API key field on Setup screen (collapsible panel)
- [x] Complete frontend redesign: "Nordic Precision" (Outfit + DM Sans + JetBrains Mono, glass-morphism, gradient accents)
- [x] Fix responsiveness issues (font-family quoting bug, overflow-x safety net)
- [x] UX overhaul: friendlier step names, inline guidance, no-blocker language
- [x] Replace hover tooltips with visible inline file descriptions
- [x] Add priority URL cross-validation against crawl data (green/yellow/red match indicator)
- [x] Fix `url_entries` undefined variable bug in run_ai_analysis
- [x] Block analysis when AI is not connected (no partial results)
- [x] Improve analyzing screen: pulsing animation, "first call takes 15-30s" message, instant timer update
- [x] Add per-batch retry (1 retry with 3s delay) and show actual error details
- [x] Add optional 3rd upload: full site URL list for true orphan detection
- [x] Redesign upload section: each field in native `st.container(border=True)`, compact labels
- [x] Add substring pattern matching for custom exclusions (e.g. "-x-")
- [x] Show custom patterns as removable tags below input field
- [x] Fix Browse & Select: bulk checkbox mode with search filter + explicit apply button
- [x] Add back navigation (tertiary buttons) on Step 1 and Step 2
- [x] Block "Next" on Upload step when AI not connected (red warning + disabled button)
- [x] Auto-scroll to top on analyzing and results screens

## Phase 9: Team Feedback & Polish
- [ ] Share app with 2-3 testers
- [ ] Collect feedback via Google Doc (template created)
- [ ] Process feedback — prioritize issues and feature requests
- [ ] Implement high-priority fixes from feedback
- [ ] Merge feature branch to main when stable

## Future: Advanced PageRank (v2)
- [ ] Weighted PageRank based on link placement (content links worth more than sidebar/footer)
- [ ] Link position ponderation (above-the-fold vs bottom of page, first link vs last)
- [ ] External link dilution (pages with many outbound external links lose more internal PR)
- [ ] Nofollow handling (nofollow links don't pass PR)
- [ ] Compare basic vs advanced PR to surface pages where placement matters most
