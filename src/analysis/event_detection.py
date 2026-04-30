"""Event status detection (Rule 17 + C3 recurring-event redirect workflow).

Two responsibilities:

1. ``is_past_event`` — heuristic flag used by the relevance scorer to apply
   a -30 penalty on past-event timely pages. Recurring-event series are EXEMPT
   from the penalty here because they're typically redirected to the current
   edition (handled by C3 instead).

2. ``find_recurring_event_redirects`` (C3) — given a set of URLs, identify
   past-edition pages that should 301-redirect to the most recent edition of
   the same series. Surfaced as a separate section in the linking plan output.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

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

YEAR_RE = re.compile(r"(?:19|20)\d{2}")


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


# --------------------------------------------------------------------------- #
# C3 — Recurring-event redirect workflow
# --------------------------------------------------------------------------- #

# Stripped suffix patterns: 2024-25 → "", 2024_2025 → "", -2024 → "", etc.
_YEAR_SUFFIX_RE = re.compile(
    r"[-_/](?:19|20)\d{2}(?:[-_/](?:19|20)\d{2}|[-_/]\d{2}|s)?$"
)


def _series_key(url_path: str, series_keyword: str) -> str:
    """Build a stable series identifier by stripping year tokens from the path.

    Example:
      `/news/world-cup-2022/` + 'world-cup' → 'news/world-cup'
      `/it/calcio/premier-league-2023-24/` + 'premier-league' → 'it/calcio/premier-league'
    """
    cleaned = url_path.strip("/").lower()
    cleaned = re.sub(r"(?:19|20)\d{2}([-_/]\d{2,4})?", "", cleaned)
    cleaned = re.sub(r"[-_/]+", "-", cleaned).strip("-/")
    return cleaned


def find_recurring_event_redirects(
    urls: list[str] | set[str],
    today: datetime | None = None,
) -> list[dict]:
    """Detect past-edition pages that should 301-redirect to the current edition.

    Algorithm: group URLs by (series keyword, year-stripped path key). Within
    each group, the URL with the most recent year is the current edition; all
    others with older years are redirect candidates pointing to that current
    URL. Groups without a current edition in the crawl yield no candidates.

    Returns a list of dicts:
        {
            "past_url": "https://.../world-cup-2022/",
            "current_url": "https://.../world-cup-2026/",
            "series": "world-cup",
            "past_year": 2022,
            "current_year": 2026,
        }
    """
    today = today or datetime.now()
    current_year = today.year

    # Group: (series, key) -> list of (year, url)
    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}

    for url in urls:
        if not url:
            continue
        try:
            path = urlparse(url).path
        except Exception:
            continue
        haystack = (path or "").lower()
        series = next((kw for kw in RECURRING_KEYWORDS if kw in haystack), None)
        if not series:
            continue
        years = [int(y) for y in YEAR_RE.findall(haystack)]
        if not years:
            continue
        year = max(years)
        key = (series, _series_key(path, series))
        groups.setdefault(key, []).append((year, url))

    candidates: list[dict] = []
    for (series, _), entries in groups.items():
        if len(entries) < 2:
            continue
        entries.sort(reverse=True)  # most recent first
        current_year_in_group, current_url = entries[0]
        # Skip if the latest is itself a past edition with no future replacement
        if current_year_in_group < current_year - 1:
            # Only redirect when the "current" really IS this year or last year
            # (avoids treating /worldcup-2018/ → /worldcup-2022/ as a fresh redirect
            # when both editions are stale).
            continue
        for past_year, past_url in entries[1:]:
            candidates.append({
                "past_url": past_url,
                "current_url": current_url,
                "series": series.replace("_", "-").rstrip("-"),
                "past_year": past_year,
                "current_year": current_year_in_group,
            })

    candidates.sort(key=lambda c: (c["series"], -c["past_year"]))
    return candidates
