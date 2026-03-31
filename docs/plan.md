# Technical Plan — Internal Link Analyzer

**Created**: 2026-02-19
**Status**: Approved

---

## 1. Tech Stack

### Backend & Frontend: Streamlit (Python)

**What it is**: Streamlit is a Python framework that lets you build web apps entirely in Python — no HTML, CSS, or JavaScript needed. You write Python, and it generates an interactive web UI automatically.

**Why I'm recommending it**:
- **Fastest to build** — probably 3-5x faster than building a separate frontend. Given the tight timeline, this is the single biggest win.
- **Perfect match for the UX** — Streamlit's natural model is a single page that runs top-to-bottom. That's exactly what the PRD describes: upload → clean → analyze → results, all flowing down the page.
- **Built-in everything we need** — file upload widgets, interactive tables with checkboxes, charts, download buttons, password auth. All out of the box.
- **Python-only** — all data processing, AI calls, and UI live in one language. No frontend/backend split to manage.
- **Easy to deploy** — can run on any server with `streamlit run app.py`, or deploy to Streamlit Cloud for free.

**Trade-off**: Streamlit gives less pixel-perfect control over the UI than a custom frontend. For 3-5 technical SEO users, this is fine. If the tool grows to a wider audience later, we can always rebuild the frontend.

### Key Python Libraries

| Library | What it does | Why this one |
|---------|-------------|--------------|
| **pandas** | CSV parsing & data manipulation | Industry standard for tabular data. Handles 40K+ rows easily. |
| **networkx** | PageRank calculation | Has a built-in `pagerank()` function. No need to implement the algorithm ourselves. |
| **anthropic** | Claude API calls | Official Anthropic Python SDK. Clean, well-documented. |
| **plotly** | Interactive charts | Works natively with Streamlit. Charts are hoverable, zoomable. |
| **openpyxl** | Excel file generation | Standard library for creating .xlsx files from Python. |

**No database needed** — v1 is stateless. Each analysis is process-and-display. Nothing is stored.

---

## 2. Architecture & Data Flow

### File Structure

```
src/
├── app.py                → Main Streamlit app (entry point)
├── config.py             → Settings, API key, constants
├── parsers/
│   ├── screaming_frog.py → Parse & validate Screaming Frog CSV
│   └── priority_urls.py  → Parse & validate Priority URLs CSV
├── cleaning/
│   ├── link_position.py  → Step 1: filter by Link Position
│   └── url_patterns.py   → Step 2: detect & filter URL patterns
├── analysis/
│   ├── link_audit.py     → Compute link stats (orphans, distribution, etc.)
│   ├── pagerank.py       → Build link graph, run PageRank
│   └── ai_analyzer.py    → Claude API: semantic analysis & anchor suggestions
├── export/
│   └── excel.py          → Generate Excel linking plan
└── ui/
    └── components.py     → Reusable UI pieces (stat cards, tables, etc.)
```

### Data Flow

```
[Screaming Frog CSV] → Parse → Validate columns
                              ↓
                    [Raw link data: 40K+ rows]
                              ↓
                    Step 1: Filter by Link Position
                    (keep Content, remove Nav/Header/Footer)
                              ↓
                    Step 2: Filter by URL patterns
                    (user toggles which patterns to exclude)
                              ↓
                    [Cleaned link data]
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
        Link Audit      PageRank Calc    [Priority URLs CSV]
        (stats,         (networkx)            ↓
         orphans,            ↓           Merge with link data
         distribution)       ↓               ↓
              ↓          PageRank scores      ↓
              ↓               ↓               ↓
              └───────────────┼───────────────┘
                              ↓
                    AI Analysis (Claude API)
                    - Cocoon detection (operator grouping)
                    - Intra-cocoon link analysis
                    - Semantic matching
                    - Linking opportunities
                    - Anchor text suggestions
                    - PageRank strategy
                              ↓
              ┌───────────────┼───────────────┐
              ↓                               ↓
        Web Dashboard                   Excel Download
        (Streamlit UI)                  (openpyxl)
```

### AI Batching Strategy (keeping costs low)

We won't send all 10,000 pages to Claude — that would be slow and expensive. Instead:

1. **Local analysis first**: Compute all link stats, PageRank, orphans, and priority URL health locally using pandas/networkx. This is instant and free.
2. **Identify interesting pages**: Priority URLs + top-50 PageRank pages + orphan pages. Typically 100-300 pages.
3. **Batch into groups of ~50 pages**: Send each batch to Claude with structured context (URL slug, existing anchors, target keyword, content type, PageRank score, inbound link count).
4. **Claude's job**: Detect operator-based cocoons (group pages by operator), analyze intra-cocoon linking, find semantic matches between pages, suggest links that strengthen cocoons (especially funneling authority to code pages), and write anchor texts.

Estimated API cost: **~$0.50-2.00 per analysis** (4-8 API calls per run).

---

## 3. Wireframes

### Login Screen
```
┌──────────────────────────────────────────────────────┐
│                                                      │
│              Internal Link Analyzer                  │
│                                                      │
│              ┌──────────────────────┐                │
│              │ Enter password       │                │
│              └──────────────────────┘                │
│              [ Access →]                             │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### File Upload (after login)
```
┌──────────────────────────────────────────────────────┐
│  Internal Link Analyzer                              │
│──────────────────────────────────────────────────────│
│                                                      │
│  Upload your files                                   │
│                                                      │
│  ┌────────────────────────┐  ┌─────────────────────┐ │
│  │  Screaming Frog CSV    │  │  Priority URLs CSV  │ │
│  │                        │  │                     │ │
│  │  Drag & drop or browse │  │  Drag & drop or     │ │
│  │                        │  │  browse              │ │
│  │  All Inlinks export    │  │  URL, Keyword,      │ │
│  │  (.csv)                │  │  Content Type (.csv) │ │
│  └────────────────────────┘  └─────────────────────┘ │
│                                                      │
│  ✓ bolavip_inlinks.csv (44,041 rows loaded)          │
│  ✓ priority_urls.csv (85 URLs loaded)                │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Cleaning Wizard — Step 1: Link Position
```
┌──────────────────────────────────────────────────────┐
│  Step 1 of 2 — Filter by Link Position               │
│──────────────────────────────────────────────────────│
│                                                      │
│  We found these link positions in your data:         │
│                                                      │
│  ┌──────────────┬──────────┬────────────────┐        │
│  │ Position     │ Count    │ Action         │        │
│  ├──────────────┼──────────┼────────────────┤        │
│  │ Content      │  24,567  │ ✅ Keep        │        │
│  │ Navigation   │  11,234  │ ❌ Remove      │        │
│  │ Header       │   4,567  │ ❌ Remove      │        │
│  │ Footer       │   2,890  │ ❌ Remove      │        │
│  │ Aside        │     783  │ ❌ Remove      │        │
│  └──────────────┴──────────┴────────────────┘        │
│                                                      │
│  Summary: Keeping 24,567 content links               │
│           (removed 19,474 non-content links)         │
│                                                      │
│  [ Confirm & Continue →]                             │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Cleaning Wizard — Step 2: URL Patterns
```
┌──────────────────────────────────────────────────────┐
│  Step 2 of 2 — Filter URL Patterns                   │
│──────────────────────────────────────────────────────│
│                                                      │
│  We detected these recurring URL patterns.           │
│  Uncheck patterns you want to exclude:               │
│                                                      │
│  ┌──────────────┬───────────────────┬──────┬──────┐  │
│  │ Keep │ Pattern       │ Example URL       │ Links│  │
│  ├──────┼───────────────┼───────────────────┼──────┤  │
│  │  ☑   │ /noticias/*   │ /noticias/liga..  │ 4,521│  │
│  │  ☑   │ /apuestas/*   │ /apuestas/mej..  │ 2,345│  │
│  │  ☐   │ /autor/*      │ /autor/juan-p..  │   890│  │
│  │  ☐   │ /page/*       │ /page/2           │   567│  │
│  │  ☐   │ /tag/*        │ /tag/premier-..  │   345│  │
│  │  ☑   │ /pronosticos/*│ /pronosticos/..  │ 1,234│  │
│  └──────┴───────────────┴───────────────────┴──────┘  │
│                                                      │
│  + Add custom pattern: [________________] [Add]      │
│                                                      │
│  Summary: Keeping 8,100 links (excluded 1,802)       │
│                                                      │
│  [ Confirm & Run Analysis →]                         │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Results — Overview Stats
```
┌──────────────────────────────────────────────────────┐
│  Analysis Results                                    │
│──────────────────────────────────────────────────────│
│                                                      │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌───────┐ │
│  │   2,345   │ │   8,100   │ │    23    │ │  3.5  │ │
│  │   Pages   │ │   Links   │ │ Orphans  │ │Avg/pg │ │
│  └───────────┘ └───────────┘ └──────────┘ └───────┘ │
│                                                      │
│  Links per page:  min 0  ·  avg 3.5  ·  max 47      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Results — PageRank Distribution
```
┌──────────────────────────────────────────────────────┐
│  PageRank Distribution                               │
│──────────────────────────────────────────────────────│
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │                                                │  │
│  │  ▓▓▓                                          │  │
│  │  ▓▓▓▓▓▓▓▓                                     │  │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                            │  │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓               │  │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                      │  │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓                                │  │
│  │  ▓▓▓▓▓                                        │  │
│  │  ▓▓                                           │  │
│  │──────────────────────────────────────────────  │  │
│  │  Low PR ──────────────────────────── High PR   │  │
│  │                                                │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Top 10 pages by PageRank:                           │
│  ┌──────────────────────────────────┬─────────────┐  │
│  │ URL                              │ PageRank    │  │
│  ├──────────────────────────────────┼─────────────┤  │
│  │ /mx/apuestas                     │ 0.0456      │  │
│  │ /mx/apuestas/mejores-casas       │ 0.0321      │  │
│  │ ...                              │ ...         │  │
│  └──────────────────────────────────┴─────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Results — Cocoon Health
```
┌──────────────────────────────────────────────────────┐
│  Cocoon Health (Operator Silos)                      │
│──────────────────────────────────────────────────────│
│                                                      │
│  ┌──────────┬───────┬────────────┬──────┬─────────┐  │
│  │ Operator │ Pages │ Intra-links│ Code │ Health  │  │
│  ├──────────┼───────┼────────────┼──────┼─────────┤  │
│  │ 1xbet    │   5   │   8 / 20   │  3→  │ 🟡 Weak │  │
│  │ Betclic  │   4   │  10 / 12   │  6→  │ 🟢 Good │  │
│  │ Caliente │   3   │   1 / 6    │  0→  │ 🔴 Poor │  │
│  │ bet365   │   6   │  14 / 30   │  5→  │ 🟡 Weak │  │
│  └──────────┴───────┴────────────┴──────┴─────────┘  │
│                                                      │
│  Intra-links: existing / possible links within silo  │
│  Code →: inbound links to the code page from siblings│
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Results — Priority URLs Health
```
┌──────────────────────────────────────────────────────┐
│  Priority URLs Health                                │
│──────────────────────────────────────────────────────│
│                                                      │
│  ┌──────┬─────────────────┬─────────┬─────┬────┬──┐  │
│  │Health│ URL              │ Keyword │Links│ PR │CT│  │
│  ├──────┼─────────────────┼─────────┼─────┼────┼──┤  │
│  │  🔴  │ /apuestas/cod.. │ codigo  │   1 │.001│CP│  │
│  │  🟡  │ /apuestas/mej.. │ mejores │   4 │.012│CO│  │
│  │  🟢  │ /apuestas/bon.. │ bono    │  14 │.034│CP│  │
│  │  🔴  │ /casino/guia..  │ guia    │   0 │  0 │GU│  │
│  └──────┴─────────────────┴─────────┴─────┴────┴──┘  │
│                                                      │
│  🔴 Critical (<3 links)  🟡 Warning (3-7)  🟢 Good (8+)│
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Results — AI Recommendations
```
┌──────────────────────────────────────────────────────┐
│  AI Link Recommendations                  47 found   │
│──────────────────────────────────────────────────────│
│                                                      │
│  Filter: [All ▾]  [To add ▾]  [To remove ▾]         │
│                                                      │
│  ┌──────────────────┬──────────────────┬──────────┐  │
│  │ Source URL        │ Target URL       │ Status   │  │
│  ├──────────────────┼──────────────────┼──────────┤  │
│  │ /noticias/liga.. │ /apuestas/cod..  │ to add   │  │
│  │ Anchor: "código promocional Betclic"            │  │
│  │ Reason: High-PR source (0.028), target is a     │  │
│  │ code page with only 1 inbound link. Semantically│  │
│  │ related: both cover Liga MX betting.            │  │
│  ├──────────────────┼──────────────────┼──────────┤  │
│  │ /apuestas/mej.. │ /casino/guia..   │ to add   │  │
│  │ Anchor: "guía de casino en línea"               │  │
│  │ Reason: Target is an orphan page (0 links).     │  │
│  │ Source has strong authority and related topic.   │  │
│  └──────────────────┴──────────────────┴──────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  📥 Download Excel Linking Plan (.xlsx)       │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 4. Build Phases

### Phase 1: Foundation (CSV parsing + cleaning wizard)
Build the skeleton app, file uploads, and the two-step cleaning wizard. At the end of this phase, a user can upload files and clean the data.

### Phase 2: Analysis Engine (link audit + PageRank)
Add the local analysis: link stats, orphan detection, PageRank calculation. At the end of this phase, the dashboard shows overview stats and PageRank distribution.

### Phase 3: AI Intelligence (Claude API)
Integrate the Claude API for cocoon detection (auto-grouping pages by operator), intra-cocoon link analysis, semantic matching, linking opportunities, and anchor text suggestions. The AI prioritizes recommendations that strengthen cocoons and funnel authority toward code pages. At the end of this phase, the cocoon health section and AI recommendations are populated.

### Phase 4: Export & Polish
Add Excel download, authentication, error handling, and visual polish. At the end of this phase, the tool is complete and usable.

### Phase 5: Testing with Real Data
Test with the real Screaming Frog export (44K rows), fix edge cases, and validate performance.

---

## 5. Key Technical Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Framework | Streamlit | Fastest path to a working tool. Single language (Python). Built-in UI components match all our needs. |
| PageRank | networkx library | Battle-tested implementation. Handles 10K-node graphs in seconds. |
| Charts | Plotly | Interactive (hover, zoom). Native Streamlit integration. |
| AI model | Claude Sonnet (latest) | Best balance of quality and speed for semantic analysis. Cheaper and faster than Opus, smarter than Haiku. |
| Excel | openpyxl | Standard Python library for .xlsx generation. |
| State management | Streamlit session_state | Built-in. Tracks wizard progress and analysis results without a database. |
| Deployment | Local / Streamlit Cloud | Start local, can deploy to Streamlit Cloud later for team access. |

---

*This plan is ready for Laura's review. No code will be written until approved.*
