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

# Phase 11 / B1 — embeddings-based candidate generation. When enabled, the
# pipeline runs Gemini text embeddings + cosine similarity + hard-filter
# pre-filtering BEFORE the recommendation AI calls, then passes the shortlist
# as hints in the prompt. Falls back to the legacy open-ended path if
# embedding generation fails. Default ON; set ILA_USE_EMBEDDINGS=0 to disable.
ILA_USE_EMBEDDINGS = os.environ.get("ILA_USE_EMBEDDINGS", "1").lower() not in ("0", "false", "no", "off")

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
