"""Market / language detection from URL patterns (linking-rules.md section 5).

Resolves the market for a site so the linking engine can block cross-market
recommendations. Auto-detects unambiguous cases; reports ambiguous cases so
the UI can prompt the user to specify.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

# ISO 3166 alpha-2 country codes (most common — extend as needed)
COUNTRY_CODES = {
    "ar", "au", "at", "be", "br", "bg", "ca", "cl", "co", "cz", "dk", "ee",
    "fi", "fr", "de", "gr", "hu", "in", "id", "ie", "it", "jp", "lv", "lt",
    "lu", "mx", "nl", "nz", "no", "pe", "ph", "pl", "pt", "ro", "ru", "sk",
    "si", "es", "se", "ch", "tr", "ua", "uk", "us", "ve", "za",
}

# Geo TLDs → market country
GEO_TLDS = {
    ".br": "br", ".fr": "fr", ".de": "de", ".it": "it", ".es": "es",
    ".uk": "uk", ".co.uk": "uk", ".us": "us", ".ca": "ca", ".mx": "mx",
    ".ar": "ar", ".cl": "cl", ".co": "co", ".pe": "pe", ".ve": "ve",
    ".au": "au", ".nz": "nz", ".jp": "jp", ".in": "in", ".za": "za",
    ".at": "at", ".be": "be", ".ch": "ch", ".dk": "dk", ".fi": "fi",
    ".gr": "gr", ".ie": "ie", ".nl": "nl", ".no": "no", ".pl": "pl",
    ".pt": "pt", ".ro": "ro", ".se": "se", ".tr": "tr", ".ua": "ua",
}

# Pure language codes (ambiguous market)
LANG_ONLY_CODES = {"en", "es", "pt", "fr", "de", "it", "ru", "zh", "ja", "ar", "nl", "sv", "no", "da", "fi", "pl", "tr", "el", "cs", "ro"}

# BCP 47 pattern: lang-COUNTRY (e.g. pt-br, en-gb, es-mx)
BCP47_RE = re.compile(r"^([a-z]{2})-([a-z]{2})$", re.IGNORECASE)


def _hostname_signal(host: str) -> tuple[str | None, str]:
    """Inspect a hostname for market signals (TLD + subdomain).

    Returns (market_code, source) or (None, "ambiguous-tld") for generic TLDs.
    """
    host = host.lower().lstrip("www.")
    # Multi-part TLD first
    for tld, market in sorted(GEO_TLDS.items(), key=lambda kv: -len(kv[0])):
        if host.endswith(tld):
            return market, f"geo TLD {tld}"

    # Subdomain like br.site.com / mx.site.com
    parts = host.split(".")
    if len(parts) >= 3:
        sub = parts[0]
        if sub in COUNTRY_CODES:
            return sub, f"market subdomain ({sub}.)"
        if sub in LANG_ONLY_CODES:
            return None, f"language-only subdomain ({sub}.) — ambiguous"

    return None, "generic TLD — ambiguous"


def _path_signal(path: str) -> tuple[str | None, str]:
    """Look at the first path segment for market signals."""
    segs = [s for s in path.split("/") if s]
    if not segs:
        return None, "no path segment"
    first = segs[0].lower()

    # BCP 47 lang-country
    m = BCP47_RE.match(first)
    if m:
        country = m.group(2).lower()
        if country in COUNTRY_CODES:
            return country, f"language-market subfolder /{first}/"

    # Pure ISO country
    if first in COUNTRY_CODES:
        return first, f"country subfolder /{first}/"

    # Pure language (ambiguous)
    if first in LANG_ONLY_CODES:
        return None, f"language-only subfolder /{first}/ — ambiguous"

    return None, "no market in path"


def detect_market(urls: list[str], sample_size: int = 200) -> dict:
    """Detect the site's market from a sample of URLs.

    Returns a dict:
      {
        "status": "resolved" | "ambiguous" | "multi-market",
        "market": "br" | "fr" | ... (when resolved),
        "candidates": ["br", "ar"] (when multi-market),
        "evidence": "geo TLD .br" | "country subfolder /br/" | ...,
        "needs_user_input": bool,
      }
    """
    if not urls:
        return {"status": "ambiguous", "needs_user_input": True, "evidence": "no URLs"}

    sample = urls[:sample_size]
    host_markets: Counter = Counter()
    path_markets: Counter = Counter()
    evidence_samples: list[str] = []

    for u in sample:
        try:
            p = urlparse(u)
        except Exception:
            continue
        host_market, host_evidence = _hostname_signal(p.netloc)
        if host_market:
            host_markets[host_market] += 1
            if host_evidence not in evidence_samples:
                evidence_samples.append(host_evidence)
        path_market, path_evidence = _path_signal(p.path)
        if path_market:
            path_markets[path_market] += 1
            if path_evidence not in evidence_samples:
                evidence_samples.append(path_evidence)

    # Hostname signal wins when present (it's site-wide)
    if host_markets:
        if len(host_markets) == 1:
            market = next(iter(host_markets))
            return {
                "status": "resolved",
                "market": market,
                "evidence": evidence_samples[0] if evidence_samples else "hostname",
                "needs_user_input": False,
            }
        # Multiple host markets — unusual (multi-domain crawl)
        return {
            "status": "multi-market",
            "candidates": list(host_markets.keys()),
            "evidence": "multiple hostname markets detected",
            "needs_user_input": True,
        }

    # Fall back to path signals
    if path_markets:
        if len(path_markets) == 1:
            market = next(iter(path_markets))
            return {
                "status": "resolved",
                "market": market,
                "evidence": evidence_samples[0] if evidence_samples else "path",
                "needs_user_input": False,
            }
        return {
            "status": "multi-market",
            "candidates": list(path_markets.keys()),
            "evidence": f"multiple market subfolders: {', '.join(path_markets.keys())}",
            "needs_user_input": True,
        }

    return {
        "status": "ambiguous",
        "evidence": evidence_samples[0] if evidence_samples else "no market signal in URLs",
        "needs_user_input": True,
    }


def market_for_url(url: str) -> str | None:
    """Return the market code for a single URL (best-effort)."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    market, _ = _hostname_signal(p.netloc)
    if market:
        return market
    market, _ = _path_signal(p.path)
    return market
