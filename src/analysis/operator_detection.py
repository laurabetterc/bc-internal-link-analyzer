"""Deterministic operator-cocoon detection from URL slugs.

Runs BEFORE the AI cocoon detector to catch operator brands that the AI
might miss because their pages aren't in the priority list / top-PR /
orphan set (and so don't make it into the AI's working contexts).

The AI detector is still authoritative — it gets to classify page types
and refine cocoons. This module's job is to ensure no operator brand with
2+ pages slips through invisibly. We pass detected brands as a hint AND
merge any operator the AI missed back into the final cocoon list.

Heuristic: tokens in URL slugs that
  - are alphanumeric (allows bet365, 1xbet, 10bet)
  - contain at least one letter (filters pure-number paths)
  - are >=4 chars
  - are NOT in GENERIC_STOPLIST (filters apuestas, casino, mejores, ...)
  - appear in >=2 distinct URLs

are candidate operator brands. URLs sharing such a token cluster into a
cocoon. URLs containing multiple such tokens (e.g. "bet365 vs betano") are
multi-operator pages.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlparse


# --------------------------------------------------------------------------- #
# Operator-context tokens — words that, when present in a URL slug, signal
# the URL is about a betting operator. We only consider URLs containing at
# least one of these tokens for brand detection. Without this filter, match
# prediction URLs like /pronosticos/arsenal-vs-real-madrid pollute detection
# with team / competition names ("madrid", "arsenal", "copa").
# --------------------------------------------------------------------------- #

OPERATOR_CONTEXT_TOKENS: set[str] = {
    # Product page types (singular + common-language variants)
    "codigo", "codigos", "code", "codes",
    "promo", "promocional", "promociones", "promocode",
    "bono", "bonos", "bonus", "bonuses",
    "opinion", "opiniones", "review", "reviews", "avis", "recensione", "recensioni",
    "test", "bewertung",  # de — review
    # Mobile / streaming
    "app", "apps", "aplicacion", "application",
    "streaming", "directo", "diretta",
    # Money / mechanics
    "cashout", "pago", "pagos", "payment", "payments", "pagamentos",
    "registro", "registrarse", "register", "registration",
    # Customer
    "atencion",  # "atencion al cliente"
}


# --------------------------------------------------------------------------- #
# Stoplist — generic SEO/path tokens we never want to mistake for operators.
# Lowercase, ASCII-only. Add tokens here as new false positives are spotted.
# --------------------------------------------------------------------------- #

GENERIC_STOPLIST: set[str] = {
    # Path/section types
    "apuestas", "apuesta", "casino", "casinos", "poker", "sports", "sport",
    "bingo", "lottery", "loteria", "loterias",
    # Product-vertical-y (also in OPERATOR_CONTEXT_TOKENS — but we filter
    # them out from brand candidates so the brand TOKEN is what's left)
    "codigos", "codigo", "code", "codes", "promo", "promociones", "promocional",
    "promocode", "bono", "bonos", "bonus", "bonuses", "bienvenida", "welcome",
    "gratis", "free", "freebets", "exclusivo", "exclusive", "especial", "special",
    "guias", "guia", "guide", "guides", "tutorial", "tutoriales",
    "review", "reviews", "opinion", "opiniones", "avis", "recensione", "recensioni",
    "app", "apps", "aplicacion", "aplicaciones", "application",
    "streaming", "directo", "live", "vivo", "diretta",
    "pago", "pagos", "payment", "payments", "pagamentos", "metodos", "methods",
    "cashout", "odds", "cuotas", "quote",
    "registro", "registrarse", "register", "registration",
    "atencion", "cliente", "service",
    "deposito", "depositos", "deposit", "deposits",
    "bonificacion", "bonificaciones",
    "promocion",  # singular form of promociones
    "viva",  # generic ("apuestas en vivo")
    # Audience / market terms
    "deportivas", "deportivos", "deportes", "casas", "house",
    "mejores", "mejor", "best", "top", "tops",
    # Site / system sections
    "news", "noticias", "blog", "blogs", "tips", "predicciones", "predictions",
    "articulo", "articulos", "article", "articles",
    "tag", "tags", "category", "categoria", "categorias",
    "match", "matches", "partido", "partidos",
    "team", "teams", "equipo", "equipos",
    "pronosticos", "pronostico", "prediction",
    "copa", "liga", "premier", "champions", "europa",
    "mundial", "world", "cup",
    # Country / locale codes & common country names
    "mexico", "mexique", "argentina", "espana", "espanol", "espanola",
    "brasil", "brazil", "colombia", "chile", "peru", "venezuela",
    "italia", "italy", "italiano", "italiana",
    "france", "francais", "francaise", "deutschland", "german", "deutsch",
    "portugal", "portugues", "portuguesa",
    # Generic English & Romance language stop-likes that survive 4-char filter
    "para", "with", "from", "into", "this", "that", "your", "more",
    "casa", "como", "sobre", "todos", "todas",
    "page", "site", "home", "index", "main",
    # Numbers-as-words that look like brands but aren't
    "year", "month", "week", "day",
    # Generic ad-hoc
    "info", "data", "list", "lista", "video", "videos",
}


# --------------------------------------------------------------------------- #
# Slug → page-type heuristics. Used to assign canonical types to deterministic
# cocoons so they pass through the rest of the pipeline (orphan guarantee,
# link budget, relevance scoring) like AI-detected cocoons.
# --------------------------------------------------------------------------- #

_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(codigo|codigos|code|codes|promo[\-_]?code)\b"), "code"),
    (re.compile(r"\b(opinion|opiniones|review|reviews|avis|recensione|recensioni|test|bewertung)\b"), "review"),
    (re.compile(r"\b(bono|bonos|bonus|bonuses|bienvenida|welcome[\-_]?bonus)\b"), "bonus"),
    (re.compile(r"\b(app|apps|aplicacion|application)\b"), "app"),
    (re.compile(r"\b(streaming|directo|live[\-_]?streaming|diretta|vivo)\b"), "streaming"),
    (re.compile(r"\b(pago|pagos|payment|payments|metodos|methods)\b"), "payment"),
    (re.compile(r"\b(cashout|cash[\-_]?out)\b"), "cashout"),
    (re.compile(r"\b(odds|cuotas|quote)\b"), "odds"),
    (re.compile(r"\b(registr|register|registration)\b"), "registration"),
    (re.compile(r"\b(customer[\-_]?service|atencion[\-_]?al[\-_]?cliente|servicio)\b"), "customer-service"),
    (re.compile(r"\b(vip|vip[\-_]?program)\b"), "vip-program"),
    (re.compile(r"\b(license|licencia)\b"), "license-info"),
]


def infer_page_type_from_slug(url: str) -> str | None:
    """Best-effort canonical type inference from URL path.

    Returns None if no pattern matches. Used as a secondary signal — the AI's
    classification still wins when both are present.
    """
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return None
    for pattern, ptype in _TYPE_PATTERNS:
        if pattern.search(path):
            return ptype
    return None


# --------------------------------------------------------------------------- #
# Token extraction
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_LETTER_RE = re.compile(r"[a-z]")


def _slug_tokens(url: str) -> list[str]:
    """Tokenize a URL path into lowercase alphanumeric chunks."""
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return []
    return _TOKEN_RE.findall(path)


def _is_brand_candidate(token: str) -> bool:
    """Return True if the token could plausibly be an operator brand."""
    if len(token) < 4:
        return False
    if token in GENERIC_STOPLIST:
        return False
    if not _LETTER_RE.search(token):
        # Pure-numeric tokens (years, IDs) — never brands
        return False
    return True


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

def _is_operator_context_url(url: str) -> bool:
    """True iff the URL slug contains at least one operator-context token.

    Filters match-prediction URLs (/pronosticos/team-vs-team) and other
    generic content from brand detection.
    """
    tokens = set(_slug_tokens(url))
    return bool(tokens & OPERATOR_CONTEXT_TOKENS)


def detect_operator_cocoons(
    urls: list[str],
    min_pages: int = 2,
) -> list[dict]:
    """Detect operator cocoons from URL slugs without calling any AI.

    Two-pass design:
      1. Filter URLs to those containing at least one operator-context token
         (codigo, bono, opinion, app, etc.). Without this filter, team and
         competition names from match-prediction URLs become false-positive
         "operators".
      2. Within that filtered set, find tokens that recur in 2+ URLs and
         pass `_is_brand_candidate` (length, stoplist, has-letter checks).
         Each surviving token = a candidate operator.

    Returns a list of cocoon dicts in the same shape as ai_analyzer.detect_cocoons:
        [
            {
                "operator": "luckia",
                "code_page": "https://.../codigo-promocional-luckia",
                "pages": ["url1", "url2", ...],
                "page_types": {"url1": "code", "url2": "review", ...},
                "_deterministic": True,  # marker for downstream merging
            },
            ...
        ]

    `min_pages` is the floor on cocoon size — under it, the token is too
    weak to confidently call a brand.

    NOTE on multi-operator pages: a URL containing multiple brand tokens
    (e.g. "bet365 vs betano") will appear in EVERY matching cocoon. The
    `_multi_operator_urls` side channel is set on the first cocoon if any
    such overlap exists, mirroring `ai_analyzer.detect_cocoons` behavior.
    """
    if not urls:
        return []

    # Pass 1 — restrict to operator-context URLs
    operator_urls = [u for u in urls if _is_operator_context_url(u)]
    if not operator_urls:
        return []

    # Pass 2 — token frequency scan on the filtered set
    token_urls: dict[str, set[str]] = defaultdict(set)
    for url in operator_urls:
        seen: set[str] = set()
        for tok in _slug_tokens(url):
            if tok in seen:
                continue
            if not _is_brand_candidate(tok):
                continue
            token_urls[tok].add(url)
            seen.add(tok)

    candidate_brands = {
        tok: page_set for tok, page_set in token_urls.items()
        if len(page_set) >= min_pages
    }

    # Build cocoon list. Pick a code page when one is present.
    cocoons: list[dict] = []
    url_to_brands: dict[str, list[str]] = defaultdict(list)
    for brand, page_set in candidate_brands.items():
        page_types: dict[str, str] = {}
        code_page: str | None = None
        for url in page_set:
            url_to_brands[url].append(brand)
            ptype = infer_page_type_from_slug(url)
            if ptype:
                page_types[url] = ptype
            if code_page is None and ptype == "code":
                code_page = url

        cocoons.append({
            "operator": brand,
            "code_page": code_page,
            "pages": sorted(page_set),
            "page_types": page_types,
            "_deterministic": True,
        })

    # Sort by size desc — bigger cocoons first (more confident)
    cocoons.sort(key=lambda c: len(c["pages"]), reverse=True)

    # Stash multi-operator URLs on the first cocoon (matches ai_analyzer convention)
    multi_op = {u: ops for u, ops in url_to_brands.items() if len(ops) > 1}
    if cocoons and multi_op:
        cocoons[0]["_multi_operator_urls"] = multi_op

    return cocoons


# --------------------------------------------------------------------------- #
# Merge with AI cocoons
# --------------------------------------------------------------------------- #

def merge_cocoon_lists(
    ai_cocoons: list[dict],
    deterministic_cocoons: list[dict],
) -> list[dict]:
    """Merge AI-detected cocoons with deterministic ones.

    AI cocoons are authoritative for any operator the AI saw. We add
    deterministic cocoons ONLY for operators the AI did not detect.
    Operator name matching is case-insensitive and normalizes whitespace.
    """
    if not deterministic_cocoons:
        return ai_cocoons

    def _norm(name: str) -> str:
        return re.sub(r"\s+", "", (name or "").lower())

    ai_ops = {_norm(c.get("operator", "")) for c in ai_cocoons if c.get("operator")}

    # Preserve any side channels (e.g. _multi_operator_urls) from the AI list
    out = list(ai_cocoons)

    for det in deterministic_cocoons:
        op_norm = _norm(det.get("operator", ""))
        if not op_norm or op_norm in ai_ops:
            continue
        out.append(det)

    return out


def operator_hint_for_prompt(deterministic_cocoons: list[dict], max_brands: int = 30) -> str:
    """Build a short prompt-addition listing detected brand candidates.

    Inserted into the AI cocoon-detection prompt so the AI considers these
    brands when grouping URLs. Capped at `max_brands` to keep prompt size
    in check on huge sites.
    """
    if not deterministic_cocoons:
        return ""
    brands = [c.get("operator", "") for c in deterministic_cocoons[:max_brands]]
    brands = [b for b in brands if b]
    if not brands:
        return ""
    return (
        "Pre-detected operator brand candidates (from slug analysis — "
        "use as hints, refine as needed): " + ", ".join(brands) + "."
    )
