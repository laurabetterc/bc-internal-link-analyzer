"""Event status detection (Rule 17 — partial implementation).

Heuristic detection of past-event timely pages so the relevance scorer can
apply the -30 penalty. Recurring-event series (e.g. "World Cup", "NFL Week",
"Premier League 2024-25") are EXEMPT from the penalty since they may get
redirected to the current edition.

Full AI-based event series classification is deferred — this heuristic uses
the URL year token + page type to make a conservative call.
"""

from __future__ import annotations

import re
from datetime import datetime

# Patterns that signal a recurring event series — these are EXEMPT from decay
RECURRING_KEYWORDS = (
    "world-cup", "worldcup", "world_cup",
    "premier-league", "premierleague",
    "champions-league", "championsleague",
    "super-bowl", "superbowl",
    "nba-finals", "nbafinals",
    "ufc-",
    "ryder-cup", "rydercup",
    "olympics", "olympic",
    "euros", "euro-2",
    "copa-america", "copaamerica",
    "nfl-week", "nfl_week",
    "gameweek", "matchday",
    "season-",
)

YEAR_RE = re.compile(r"(19|20)\d{2}")


def is_past_event(
    url: str,
    page_type: str | None = None,
    target_keyword: str | None = None,
    today: datetime | None = None,
) -> bool:
    """Heuristic: True only if this is a one-time past-event timely page.

    Returns False (no penalty) for recurring series, even if past — those may
    be redirected to the current edition.
    """
    if page_type and page_type != "topic-event-timely":
        return False  # only timely pages decay

    today = today or datetime.now()
    current_year = today.year

    haystack = (url + " " + (target_keyword or "")).lower()

    # Exempt recurring series
    for kw in RECURRING_KEYWORDS:
        if kw in haystack:
            return False

    # Find any year tokens — if the most recent one is in the past, treat as past event
    years = [int(y) for y in YEAR_RE.findall(haystack)]
    if not years:
        return False

    latest = max(years)
    return latest < current_year
