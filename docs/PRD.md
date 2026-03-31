# PRD: Internal Link Analyzer

**Created**: 2026-02-19
**Last updated**: 2026-02-20
**Status**: Approved

---

## 1. What Is This?

A web-based internal link analysis tool powered by AI, built for an internal SEO technical team. Users upload a Screaming Frog crawl export and a priority URLs file, and the tool automatically cleans the data, analyzes the internal link structure, calculates internal PageRank, and uses AI (Gemini API) to find linking opportunities, suggest anchor texts, and build a strategic linking plan. The output is an interactive web dashboard and a downloadable Excel spreadsheet ready for the SEO Content Manager to execute.

## 2. Why Are We Building This?

Today, internal link analysis is a painful, manual process:
1. Export inlinks from Screaming Frog
2. Manually clean the spreadsheet (remove navigation, header, footer, author pages, pagination, etc.)
3. Import into Google Sheets, cross-reference with content planning data
4. Manually check priority URLs for sufficient internal links
5. Manually find semantic match opportunities and gaps
6. Manually build a linking plan (add/remove recommendations)

This process is repeated per site, multiple times per year, and depends entirely on Laura doing it. The tool automates steps 2-6, makes it delegable to the team, and produces better results thanks to AI-powered semantic analysis and PageRank strategy.

**If we don't build this**: the team keeps doing manual, time-consuming audits that are inconsistent and hard to delegate.

### Business Impact
- **Time saved**: ~2 hours per site per audit (manual process). With 300 sites audited multiple times per year, this represents hundreds of hours annually reduced to minutes per analysis.
- **Cost impact**: Frees up senior SEO time (Laura) for strategic work instead of repetitive spreadsheet tasks. Makes audits delegable to the broader team — no longer a bottleneck on one person.
- **Strategic value**: Better internal linking directly improves rankings on key queries (the north star KPI). AI-powered analysis finds opportunities that manual review misses, and cocoon detection ensures operator silos are properly structured — a competitive edge in the iGaming niche.

## 3. Who Uses This?

### Primary Users
| Role | What they do with the tool | Technical level | Frequency |
|------|---------------------------|-----------------|-----------|
| SEO technical team (3-5 people) | Upload crawl data, run analysis, review recommendations, export linking plan | SEO professionals — understand internal linking, PageRank, anchor text | On-demand, per site, monthly or quarterly |

### Stakeholders (see results but don't use the tool)
- SEO Content Manager — receives the exported Excel linking plan and executes the recommendations (adds/removes links in the CMS)

### Adoption Considerations
- **Barriers**: Trust in AI recommendations (team needs to see that suggestions are relevant and actionable). New workflow — team is used to Laura doing this manually.
- **Training needed**: Quick demo — the tool is self-explanatory for SEO professionals. No tutorial-like hand-holding needed.
- **Replaces**: Manual Google Sheets-based audit process (steps 2-6 above)

## 4. What Does It Do? (Features)

### Must Have (MVP)

- [ ] **CSV upload**: Upload Screaming Frog "All Inlinks" export (.csv)
- [ ] **Priority URLs upload**: Upload a second CSV with columns: URL, Target Keyword
- [ ] **Guided data cleaning wizard**:
  - Step 1: Auto-filter by Link Position (keep only "Content" links, remove Navigation/Header/Footer/Aside). Show summary with counts. User confirms.
  - Step 2: Smart URL pattern detection — scan URLs, group by recurring path segments, show a table with pattern, example URL, link count, and a toggle (keep/exclude). User checks/unchecks patterns. User can also add custom patterns manually.
- [ ] **Internal link audit**:
  - Total pages, total internal links, orphan pages (zero inbound content links)
  - Links per page (inbound and outbound) — average, min, max
  - Link distribution overview
- [ ] **Internal PageRank calculation**:
  - Calculate PageRank for all pages based on the cleaned link graph
  - Visualize PageRank distribution
- [ ] **Cocoon detection & analysis**:
  - Detect operator-based cocoons: group pages that belong to the same operator (e.g., "1xbet review", "1xbet code", "1xbet app") using URL slugs, anchor texts, and keywords
  - Analyze intra-cocoon linking: are pages within each cocoon properly linked to each other?
  - Identify cocoon gaps: missing links between sibling pages, especially links pointing to the code page
  - Score each cocoon's health: how well-connected is the silo, and is the code page getting enough support from its siblings?
- [ ] **AI-powered semantic analysis** (Gemini API):
  - Analyze URL slugs, existing anchor texts, and target keywords to understand page topics
  - Find linking opportunities: pages that are semantically related but not linked
  - Detect gaps: priority pages receiving too few internal links
  - Detect unbalanced linking: pages with disproportionate inbound vs outbound links
  - Within cocoons: prioritize linking recommendations that strengthen the silo and funnel authority toward the code page
- [ ] **AI anchor text suggestions**:
  - For each recommended new link, suggest specific anchor text based on the target page's keyword and the source page's topic
- [ ] **PageRank strategy**:
  - Identify high-PageRank pages that could pass equity to low-PageRank priority URLs
  - Within cocoons: ensure the code page is the top PageRank recipient from its sibling pages
  - Recommend strategic link additions to boost priority pages
- [ ] **Interactive web dashboard** with sections:
  - Overview: total pages, total links, orphan count, average links per page
  - PageRank distribution chart
  - Cocoon health: per-operator silo overview showing cocoon completeness, intra-cocoon link count, and whether the code page is properly supported
  - Priority URLs table: each URL with current inbound link count, PageRank score, health indicator (good/warning/critical)
  - Link opportunities list: AI recommendations with source, target, suggested anchor, reason
- [ ] **Downloadable Excel spreadsheet** (linking plan):
  - Columns: Source URL, Anchor, Target URL, Status
  - Status values: "live" (existing links), "to add" (AI recommendations), "to remove" (problematic links)
  - "removed" status is for manual tracking after execution — not generated by the tool
- [ ] **AI token usage tracking**:
  - After each analysis, display: API calls count, input tokens, output tokens, thinking tokens, total tokens
  - Show estimated cost based on Gemini pricing
  - Include token usage in the Excel Summary sheet
- [ ] **Simple authentication**: Single shared password to access the tool

### Nice to Have (v2 — Later)

- [ ] Analysis history: save and compare results over time
- [ ] Google Search Console integration to auto-suggest priority pages
- [ ] Content-based semantic analysis (fetch actual page content instead of relying on URLs/anchors)
- [ ] Built-in crawler to replace Screaming Frog export
- [ ] Multi-user accounts with roles
- [ ] Automated scheduled analyses

### Out of Scope (NOT building)

- Custom web crawler (too complex for v1, users upload Screaming Frog CSV)
- Integration with other SEO tools (Ahrefs, Moz, etc.)
- External link analysis (backlinks) — this is internal links only
- Content editing or CMS integration

## 5. User Workflow

### Context: Before & After
- **Before this tool**: User exports "All Inlinks" from Screaming Frog (takes ~5 min), then prepares a priority URLs CSV from their content planning spreadsheet. This is the input.
- **Trigger**: An SEO analyst needs to audit a site's internal linking — typically during a quarterly review, after a site migration, or when priority pages aren't ranking as expected.
- **After this tool**: The analyst reviews the dashboard results, downloads the Excel linking plan, and hands it to the SEO Content Manager who executes the recommendations in the CMS (adding/removing links).

### Step-by-Step User Flow
1. User opens the web app, enters the shared password
2. User uploads the Screaming Frog CSV
3. **Cleaning wizard — Step 1**: Tool auto-filters by Link Position, shows summary ("Kept X content links, removed Y navigation/header/footer links"). User confirms.
4. **Cleaning wizard — Step 2**: Tool detects URL patterns, shows table with toggles. User checks/unchecks patterns to exclude. Can add custom patterns. Confirms.
5. User uploads the Priority URLs CSV
6. User clicks "Run Analysis"
7. Tool runs: link audit, PageRank calculation, AI semantic analysis (progress indicator shown)
8. User sees the interactive dashboard with all results
9. User reviews recommendations, explores data
10. User downloads the Excel linking plan

### Frequency & Scheduling
- **How often**: On-demand, per site. Typically monthly or quarterly per site.
- **Automation**: Manual trigger only (v1). User decides when to run an analysis.
- **Triggers/Alerts**: None in v1. User initiates each analysis.

## 6. Input

### What the User Provides
- **Screaming Frog CSV**: The "All Inlinks" export. Standard format with columns: Type, Source, Destination, Size, Alt Text, Anchor, Status Code, Status, Follow, Target, Rel, Path Type, Link Path, Link Position, Link Origin.
- **Priority URLs CSV**: 2-3 column file: `URL`, `Target Keyword`, and optionally `Content Type` (e.g., "code page", "comparator", "guide", "review", "timely content"). Typically 10-200 rows. When Content Type is provided, the AI uses it to prioritize recommendations — high-conversion pages like code pages and comparators get more aggressive linking treatment.

### Data Source
- **Origin**: Screaming Frog CSV is a direct export from the Screaming Frog desktop crawler. Priority URLs CSV is manually prepared by the analyst from their content planning spreadsheet.
- **Typical volume**: 200 to 10,000 pages per site. Screaming Frog exports can have 40,000+ rows (multiple links per page). Priority URLs typically 10-200 rows.
- **Maximum scale**: 40,000+ row CSVs (largest known export: bolavip at ~44K rows).

### Data Quality & Validation
- **Messy data handling**: Validate required column headers on upload — reject with clear error if columns don't match Screaming Frog format. Auto-filter to Hyperlink rows only (ignore images, scripts, etc.).
- **Validation rules**: Priority URLs CSV must have at least `URL` and `Target Keyword` columns. Content Type is optional. URLs must be valid format.
- **Sensitive data**: No credentials or PII in the input. URLs are internal site structure data.

## 7. Output & Deliverables

### Primary Output
- **Web dashboard**: Interactive, explorable, with charts and tables. Sections: Overview stats, PageRank distribution, Cocoon health, Priority URLs health, AI recommendations.
- **Excel spreadsheet**: The linking plan with columns Source URL, Anchor, Target URL, Status, Priority, Reason. Ready to hand to the SEO Content Manager for execution.
- **Audience**: SEO technical team reviews the dashboard. SEO Content Manager receives the Excel to execute.
- **Key metrics/insights**: Orphan page count, PageRank distribution, cocoon health scores, priority URL health (inbound links + PageRank), AI-recommended links with anchor text.

### Export & Sharing
- **Export formats**: Excel (.xlsx) with 2 sheets — "Linking Plan" (all recommendations + existing links) and "Summary" (audit stats, cocoon health, priority URL health).
- **Sharing mechanism**: Download button in the dashboard. User saves the file and shares it manually (email, Slack, etc.).
- **Historical data**: None in v1. Each analysis is standalone. User keeps the Excel file for their records.

### Visualizations
- **Charts/graphs**: PageRank distribution histogram (Plotly), overview stat cards (4 metrics), cocoon health summary cards, color-coded health indicators in tables.
- **Reference format**: No existing report to match — this is a new tool.

## 8. UX & Design

### Interface Type
- **Format**: Web app (Streamlit) — opens in any browser, no installation needed.
- **Pages/Views**: 3 distinct screens that replace each other sequentially (no tabs, sidebar, or multi-page navigation).

### Look & Feel
- **Style**: Clean and minimal — no clutter, generous whitespace, clear typography. Better Collective branding.
- **Branding**: Primary color dark forest green `#005947`, font Roboto, flat corporate aesthetic.
- **Inspiration**: Better Collective corporate website design language.
- **First impression**: Screen 2 (Setup) — clear file upload area with step indicator showing progress.

### Layout
- **Screen 1 — Login**: Centered password field. Disappears completely after authentication.
- **Screen 2 — Setup**: File uploads + cleaning wizard (both steps). Step indicator shows progress (Upload → Filter Positions → Filter Patterns). A "Run Analysis" button transitions to the results screen.
- **Screen 3 — Results**: All analysis output on one scrollable page. No setup step indicator — replaced by a results header with a "New Analysis" button to start over.
  - Overview stats (4 metric cards)
  - PageRank distribution chart
  - Cocoon health (per-operator silo analysis)
  - Priority URLs health table
  - AI link recommendations
  - Download Excel button

### Responsiveness
- **Devices**: Desktop only. This is an internal tool used by analysts at their desks.
- **Browser support**: Any modern browser (Chrome, Firefox, Edge, Safari).

### Feedback & States
- **Loading**: `st.status()` component with step-by-step progress messages during AI analysis (e.g., "Detecting cocoons...", "Analyzing batch 2/5...", "Generating recommendations...").
- **Empty states**: Setup screen shows clear upload instructions. Results screen never shows empty — only appears after analysis completes.
- **Error messages**: Plain language, actionable. E.g., "This doesn't look like a Screaming Frog export — missing columns: Source, Destination." Includes a "Try Again" button on failures.
- **Success confirmation**: Results screen appearing IS the success state. Excel download confirms with file save dialog.

### Language & Accessibility
- **Language**: English only.
- **Accessibility**: No specific requirements beyond standard web accessibility.

### Wireframes
> Full interactive HTML wireframe available at `docs/wireframe.html` (open in browser).
> Wireframes were created during the planning phase and approved by Laura.

## 9. Data & Storage

### Data Sources
- **File imports**: Screaming Frog CSV ("All Inlinks" export), Priority URLs CSV (user-prepared).
- **APIs**: Gemini 2.5 Flash (Google) for semantic analysis, cocoon detection, and anchor text suggestions.
- **Scraping**: None — all data comes from user-uploaded files.

### Data Freshness
- **Update frequency**: On-demand — each analysis uses the latest uploaded files.
- **Caching**: None. Each analysis runs fresh.

### Storage & Persistence
- **What to store**: Nothing persistent in v1. Each analysis is standalone — process, display, export, discard.
- **Retention**: No data retention. User downloads the Excel to keep results.
- **Storage type**: In-memory only (Streamlit session state). Data is gone when the session ends.

## 10. Collaboration & Access

### Authentication
- **Login required**: Yes — single shared password (default: `bcseo2026`, configurable via `ILA_PASSWORD` env var).
- **Access control**: Everyone with the password sees the same tool. No roles, no permissions.

### Multi-User
- **Concurrent use**: Yes — multiple users can run separate analyses simultaneously (each Streamlit session is independent).
- **Shared results**: No — each session is independent. Results are not shared between users.
- **Audit trail**: None in v1. No tracking of who ran what.

## 11. Error Handling & Edge Cases

### Known Edge Cases
- CSV with 0 content links after position filtering (all links are navigation/header/footer)
- Screaming Frog export with unexpected columns or format changes
- Priority URLs CSV where none of the URLs appear in the crawl data
- Very small site (<50 pages) where PageRank and cocoon analysis may be less meaningful
- Very large site (40,000+ rows) that could be slow to process
- API rate limits or timeouts during AI analysis on large sites

### Error Strategy
- **Partial results**: Yes — if AI analysis fails, the tool still shows link audit + PageRank results (the non-AI parts). Clear message explains that AI features require an API key or that the API call failed.
- **Retry logic**: "Try Again" button on failure. No automatic retries.
- **Worst case**: Wrong AI recommendations are not catastrophic — the SEO Content Manager reviews all recommendations before executing them. The tool assists, it doesn't auto-execute. Accuracy is important but not safety-critical.

### Exclusions
- Non-hyperlink link types (images, scripts, etc.) are auto-filtered during CSV parsing
- Navigation, header, footer, aside links are filtered in cleaning Step 1
- URL patterns excluded by user in cleaning Step 2 (pagination, author pages, tag pages, etc.)

## 12. Success Criteria

How we know this project is DONE and WORKING:

- [ ] Can upload a real Screaming Frog CSV (40,000+ rows) and process it without errors
- [ ] Cleaning wizard correctly separates content links from navigation/header/footer
- [ ] URL pattern detection identifies at least the obvious patterns (pagination, author, category)
- [ ] PageRank calculation produces reasonable scores for all pages
- [ ] AI identifies at least 10 relevant linking opportunities per analysis
- [ ] AI anchor text suggestions are contextually relevant (not generic)
- [ ] Priority URLs table clearly shows which pages need more internal links
- [ ] Dashboard loads in a browser without errors and is usable
- [ ] Excel export contains all recommendations in the correct format
- [ ] A team member can run an analysis independently without Laura's help
- [ ] Full analysis completes in under 5 minutes for a 10,000-page site

## 13. Constraints & Risks

- **Timeline**: TIGHT. This project must ship fast. Every decision should optimize for speed and efficiency. Nice-to-haves are strictly v2. Recommendations must prioritize the fastest path to a working tool.
- **API costs**: Gemini 2.5 Flash free tier allows 20 requests/day. For analyses requiring more, paid tier is very cheap (~$0.01-0.05 per analysis). Token usage is tracked and displayed in the dashboard.
- **API key setup**: Google Gemini API key needs to be created at https://aistudio.google.com/apikey. Steps documented in APIS.md.
- **CSV format dependency**: The tool depends on Screaming Frog's export format. If they change it, the parser breaks. Mitigation: validate column headers on upload and show a clear error.
- **Large file handling**: 40,000+ row CSVs need to be processed efficiently without crashing.
- **AI quality**: Semantic matching from URL slugs alone may miss nuance. This is acceptable for v1 — anchors and keywords compensate. v2 can add content fetching.
- **Budget**: Free/cheap tools preferred. Gemini 2.5 Flash has a free tier; paid tier is minimal cost.
- **Compliance**: No specific compliance requirements — internal tool, no user PII, no external data sharing.
- **Deadline**: Ship as fast as possible. No hard calendar date, but urgency is high.

## 14. Open Questions

- None — all questions resolved during interview.
- **Decisions made by Claude** (documented for transparency):
  - Desktop-only (no mobile) — internal tool used by analysts at desks
  - English-only — internal team, no i18n needed
  - No audit trail in v1 — small team, low complexity

## 15. References & Inspiration

- **Sample data**: Screaming Frog export available at: `/Users/lauragaiton/Desktop/Bureau - MacBook Pro de Laura/crawls/all_inlinks_bolavip.csv`
- **Screaming Frog columns used**: Type, Source, Destination, Anchor, Link Position, Status Code, Follow
- **Wireframe**: `docs/wireframe.html` — full interactive HTML mockup with BC branding
- **Design reference**: Better Collective corporate website (bettercollective.com) for brand colors and style
