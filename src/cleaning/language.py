"""Language detection and filtering for multilingual sites (Phase 11 / A4 + A5)."""

import re
from urllib.parse import urlparse

import pandas as pd


# ISO 639-1 two-letter language codes (full set per the standard).
# Restricted to two-letter codes used as URL path prefixes by BC and competitor sites.
ISO_639_1_CODES = frozenset({
    "ab", "aa", "af", "ak", "sq", "am", "ar", "an", "hy", "as", "av", "ae",
    "ay", "az", "bm", "ba", "eu", "be", "bn", "bh", "bi", "bs", "br", "bg",
    "my", "ca", "ch", "ce", "ny", "zh", "cv", "kw", "co", "cr", "hr", "cs",
    "da", "dv", "nl", "dz", "en", "eo", "et", "ee", "fo", "fj", "fi", "fr",
    "ff", "gl", "ka", "de", "el", "gn", "gu", "ht", "ha", "he", "hz", "hi",
    "ho", "hu", "ia", "id", "ie", "ga", "ig", "ik", "io", "is", "it", "iu",
    "ja", "jv", "kl", "kn", "kr", "ks", "kk", "km", "ki", "rw", "ky", "kv",
    "kg", "ko", "ku", "kj", "la", "lb", "lg", "li", "ln", "lo", "lt", "lu",
    "lv", "gv", "mk", "mg", "ms", "ml", "mt", "mi", "mr", "mh", "mn", "na",
    "nv", "nd", "ne", "ng", "nb", "nn", "no", "ii", "nr", "oc", "oj", "cu",
    "om", "or", "os", "pa", "pi", "fa", "pl", "ps", "pt", "qu", "rm", "rn",
    "ro", "ru", "sa", "sc", "sd", "se", "sm", "sg", "sr", "gd", "sn", "si",
    "sk", "sl", "so", "st", "su", "sv", "sw", "ta", "te", "tg", "th", "ti",
    "bo", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tw", "ty", "ug", "uk",
    "ur", "uz", "ve", "vi", "vo", "wa", "cy", "wo", "fy", "xh", "yi", "yo",
    "za", "zu",
})

# Display names for the most common BC markets — fallback to the raw code otherwise.
LANG_DISPLAY = {
    "en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French",
    "de": "German", "it": "Italian", "nl": "Dutch", "ru": "Russian",
    "pl": "Polish", "cs": "Czech", "sk": "Slovak", "ro": "Romanian",
    "bg": "Bulgarian", "hr": "Croatian", "sr": "Serbian", "sv": "Swedish",
    "no": "Norwegian", "da": "Danish", "fi": "Finnish", "el": "Greek",
    "tr": "Turkish", "ar": "Arabic", "he": "Hebrew", "ja": "Japanese",
    "zh": "Chinese", "ko": "Korean", "hi": "Hindi", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "hu": "Hungarian",
    "uk": "Ukrainian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian",
    "sl": "Slovenian", "ka": "Georgian",
}

ROOT_KEY = "(root)"

_LOCALE_RE = re.compile(r"^([a-z]{2})-[a-z]{2}$")


def extract_lang_segment(url: str) -> str | None:
    """Return the language code from the first path segment, or None if not a known language.

    Recognizes plain ISO 639-1 codes ('it', 'pt') and locale variants ('pt-br', 'en-us')
    as long as the leading 2-letter prefix is a known ISO code.
    """
    if not url:
        return None
    try:
        path = urlparse(url).path
    except Exception:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    seg = parts[0].lower()
    if len(seg) == 2 and seg in ISO_639_1_CODES:
        return seg
    m = _LOCALE_RE.match(seg)
    if m and m.group(1) in ISO_639_1_CODES:
        return seg
    return None


def _build_url_lang_map(df: pd.DataFrame) -> dict[str, str | None]:
    """Compute language for every unique URL once (avoids repeated urlparse on large frames)."""
    unique_urls = pd.unique(pd.concat([df["Source"], df["Destination"]]))
    return {url: extract_lang_segment(url) for url in unique_urls}


def detect_languages(df: pd.DataFrame, min_pages: int = 10) -> dict:
    """Detect language sections by ISO 639-1 first-path-segment.

    Pages without a language prefix go in the 'root' bucket (typically English on BC sites).
    Languages with fewer than min_pages pages are dropped (avoids false positives from
    accidental 2-letter slugs like '/it' as a campaign tag).

    Returns:
        dict with:
            languages: list of {code, label, page_count, link_count, example} sorted by page_count desc
            root: same fields for the no-prefix bucket (or None)
            url_lang_map: dict[url -> code | None] for downstream filtering
            total_pages: count of unique URLs across the frame
    """
    url_lang = _build_url_lang_map(df)

    # Group unique URLs by language
    urls_by_lang: dict[str | None, set[str]] = {}
    for url, lang in url_lang.items():
        urls_by_lang.setdefault(lang, set()).add(url)

    # Compute link counts per language using vectorised mapping
    src_lang = df["Source"].map(url_lang)
    dst_lang = df["Destination"].map(url_lang)

    languages = []
    for code, urls in urls_by_lang.items():
        if code is None:
            continue
        if len(urls) < min_pages:
            continue
        link_count = int(((src_lang == code) | (dst_lang == code)).sum())
        languages.append({
            "code": code,
            "label": _label_for(code),
            "page_count": len(urls),
            "link_count": link_count,
            "example": _shortest(urls),
        })
    languages.sort(key=lambda x: x["page_count"], reverse=True)

    root_urls = urls_by_lang.get(None, set())
    root = None
    if root_urls:
        root_link_count = int((src_lang.isna() | dst_lang.isna()).sum())
        root = {
            "code": ROOT_KEY,
            "label": "No prefix (root section)",
            "page_count": len(root_urls),
            "link_count": root_link_count,
            "example": _shortest(root_urls),
        }

    return {
        "languages": languages,
        "root": root,
        "url_lang_map": url_lang,
        "total_pages": len(url_lang),
    }


def _label_for(code: str) -> str:
    base = code.split("-")[0]
    name = LANG_DISPLAY.get(base, code.upper())
    return f"{name} (/{code}/)"


def _shortest(urls: set[str]) -> str:
    if not urls:
        return ""
    return min(urls, key=len)


def filter_by_language(
    df: pd.DataFrame,
    selected: str,
    url_lang_map: dict[str, str | None] | None = None,
) -> pd.DataFrame:
    """Keep only links where both Source and Destination belong to the selected section.

    selected: an ISO code ('it', 'pt-br') or ROOT_KEY for the no-prefix bucket.
    """
    if not selected:
        return df.copy()
    if url_lang_map is None:
        url_lang_map = _build_url_lang_map(df)

    src = df["Source"].map(url_lang_map)
    dst = df["Destination"].map(url_lang_map)

    if selected == ROOT_KEY:
        mask = src.isna() & dst.isna()
    else:
        mask = (src == selected) & (dst == selected)
    return df[mask].copy()


# ---- A5: Language-switcher detection -----------------------------------------

_LANG_ROOT_RE_TEMPLATE = r"^https?://[^/]+/{code}/?$"


def detect_language_switchers(
    df: pd.DataFrame,
    language_codes: list[str],
    min_page_ratio: float = 0.3,
    min_lang_root_share: float = 0.7,
) -> list[dict]:
    """Detect Link Paths (XPaths) that act as language switchers.

    A switcher path is one that:
      - appears on a meaningful share of pages (>= min_page_ratio), and
      - has destinations that are mostly language root URLs (>= min_lang_root_share).

    Returns a list of {path, page_count, page_ratio, link_count, destinations,
    target_languages} sorted by page_count desc.
    """
    if "Link Path" not in df.columns or not language_codes:
        return []

    valid_codes = [re.escape(c) for c in language_codes]
    lang_root_re = re.compile(_LANG_ROOT_RE_TEMPLATE.format(code="(?:" + "|".join(valid_codes) + ")"))

    sub = df.dropna(subset=["Link Path"]).copy()
    if sub.empty:
        return []

    sub["_is_lang_root"] = sub["Destination"].apply(lambda u: bool(lang_root_re.match(u or "")))
    sub["_dest_lang"] = sub["Destination"].apply(lambda u: extract_lang_segment(u or ""))

    total_pages = df["Source"].nunique()
    if total_pages == 0:
        return []

    grouped = sub.groupby("Link Path")
    switchers = []
    for path, group in grouped:
        link_count = len(group)
        unique_pages = group["Source"].nunique()
        page_ratio = unique_pages / total_pages
        lang_root_share = group["_is_lang_root"].mean() if link_count else 0.0
        if page_ratio < min_page_ratio:
            continue
        if lang_root_share < min_lang_root_share:
            continue
        target_langs = sorted({c for c in group["_dest_lang"].dropna().unique() if c})
        sample_dests = list(group["Destination"].drop_duplicates().head(5))
        switchers.append({
            "path": path,
            "page_count": int(unique_pages),
            "page_ratio": float(page_ratio),
            "link_count": int(link_count),
            "destinations": sample_dests,
            "target_languages": target_langs,
        })

    switchers.sort(key=lambda x: x["page_count"], reverse=True)
    return switchers
