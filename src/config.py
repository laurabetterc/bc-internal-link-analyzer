"""Configuration and constants for the Internal Link Analyzer."""

import os

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# AI batching — smaller batches work better with Gemini (avoids empty responses on large prompts)
AI_BATCH_SIZE = 20
AI_COCOON_BATCH_SIZE = 40

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
