"""Configuration and constants for the Internal Link Analyzer."""

import os

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Override at runtime with GEMINI_MODEL env var or via the UI (AI config panel).
# Verified IDs (Apr 2026): "gemini-3.1-flash-lite-preview" (default, cheap), "gemini-3-flash-preview",
# "gemini-3.1-pro-preview" (premium, expensive — thinking required), "gemini-2.5-flash" (legacy GA).
# Default chosen 2026-04-29 after cost incident — see APIS.md for context.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
# Max output tokens — lowered 32K → 8K after 2026-04-29 cost incident on 3.1 Pro Preview.
# 3.1 Flash-Lite supports up to 65,536; 8K is plenty for our batch sizes and caps thinking output.
GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "8192"))

# Dev-only UI toggles. Set ILA_DEV_MODE=1 in local .streamlit/secrets.toml to expose
# the model picker (for A/B testing). Production / Streamlit Cloud leaves it unset.
ILA_DEV_MODE = os.environ.get("ILA_DEV_MODE", "").lower() in ("1", "true", "yes")

# AI batching — smaller batches work better with Gemini (avoids empty responses on large prompts)
AI_BATCH_SIZE = 20
AI_COCOON_BATCH_SIZE = 40
# Phase 11 / B3 — pair-scoring batch size. Each pair is ~50 input tokens; 30
# keeps each call under ~2K input. Smaller batches reduce AI context-switching
# pressure on the closed-task scorer.
AI_SCORE_BATCH_SIZE = 30

# Phase 11 / B1 — embeddings-based candidate generation. When enabled, the
# pipeline runs Gemini text embeddings + cosine similarity + hard-filter
# pre-filtering BEFORE the recommendation AI calls, then passes the shortlist
# as hints in the prompt. Falls back to the legacy open-ended path if
# embedding generation fails. Default ON; set ILA_USE_EMBEDDINGS=0 to disable.
ILA_USE_EMBEDDINGS = os.environ.get("ILA_USE_EMBEDDINGS", "1").lower() not in ("0", "false", "no", "off")

# Phase 11 / B3 — closed-task per-pair scoring. When enabled (and embeddings
# are also on), the AI receives the candidate shortlist as (source, target,
# similarity) pairs and returns a score + anchor + reason per pair instead
# of doing open-ended page-batch exploration. Falls back to the legacy
# open-ended path when embeddings are off OR when this flag is off. Default
# ON; set ILA_USE_CLOSED_TASK=0 to use the legacy path.
ILA_USE_CLOSED_TASK = os.environ.get("ILA_USE_CLOSED_TASK", "1").lower() not in ("0", "false", "no", "off")
# Drop pairs whose AI score is below this threshold (matches `score_pair`'s
# pass threshold so AI's score and rule-engine's score align).
ILA_SCORE_THRESHOLD = int(os.environ.get("ILA_SCORE_THRESHOLD", "60"))

# Phase 11 / B4 — context caching. When on, score_link_pairs creates a
# Gemini context cache for the static prompt parts (rubric + cocoon summary)
# and reuses it across every scoring batch — ~10x cheaper input on cached
# tokens. Falls back silently when the cache content is too small, the
# model doesn't support caching, or creation fails. Default ON.
ILA_USE_CONTEXT_CACHE = os.environ.get("ILA_USE_CONTEXT_CACHE", "1").lower() not in ("0", "false", "no", "off")

# Phase 11 / B9 — AI working-set cap. The legacy open-ended path keeps the
# defensive 500-cap (cost there scales with page count). Closed-task mode
# scales with candidate count, not pages, so we can let the working set
# breathe — 10K is effectively unlimited for any single-language section.
ILA_MAX_AI_PAGES_LEGACY = int(os.environ.get("ILA_MAX_AI_PAGES_LEGACY", "500"))
ILA_MAX_AI_PAGES_CLOSED_TASK = int(os.environ.get("ILA_MAX_AI_PAGES_CLOSED_TASK", "10000"))


def max_ai_pages() -> int:
    """Return the working-set page cap based on the active path."""
    if ILA_USE_EMBEDDINGS and ILA_USE_CLOSED_TASK:
        return ILA_MAX_AI_PAGES_CLOSED_TASK
    return ILA_MAX_AI_PAGES_LEGACY

# Health thresholds for priority URLs
HEALTH_CRITICAL_MAX = 2  # 0-2 links = critical
HEALTH_WARNING_MAX = 7   # 3-7 links = warning
# 8+ links = good

# PageRank
PAGERANK_DAMPING = 0.85
PAGERANK_MAX_ITER = 100

# App password (set via environment variable)
APP_PASSWORD = os.environ.get("ILA_PASSWORD", "")

# Screaming Frog expected columns
SF_REQUIRED_COLUMNS = [
    "Type",
    "Source",
    "Destination",
    "Anchor",
    "Link Position",
    "Status Code",
    "Follow",
]

# Priority URLs expected columns
PRIORITY_REQUIRED_COLUMNS = ["URL", "Target Keyword"]
PRIORITY_OPTIONAL_COLUMNS = ["Content Type"]

# Link positions to keep by default
DEFAULT_KEEP_POSITIONS = ["Content"]
