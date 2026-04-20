"""AI-powered analysis using Gemini API.

Handles cocoon detection, semantic linking opportunities,
anchor text suggestions, and PageRank strategy recommendations.
Tracks token usage for cost transparency.
"""

import json
import time
from urllib.parse import urlparse

import pandas as pd
from google import genai
from google.genai import errors as genai_errors

import src.config as _config
from src.analysis.relevance_scorer import score_pair
from src.analysis.event_detection import is_past_event


# --------------------------------------------------------------------------- #
# Security — redact API keys from any user-facing string (errors, logs, UI).
# --------------------------------------------------------------------------- #
import re as _re

# Gemini keys start with "AIza" followed by 35 URL-safe chars (39 total).
_API_KEY_PATTERN = _re.compile(r"AIza[0-9A-Za-z_\-]{35}")


def _redact(text: str) -> str:
    """Remove any API key from a string before showing it to the user or logging it."""
    if not text:
        return text
    return _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", str(text))


# Token usage tracker — accumulates across all API calls in one analysis
_token_usage = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "thinking_tokens": 0,
    "total_tokens": 0,
    "api_calls": 0,
}


def reset_token_usage():
    """Reset the token counter (call at the start of each analysis)."""
    global _token_usage
    _token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "thinking_tokens": 0,
        "total_tokens": 0,
        "api_calls": 0,
    }


def get_token_usage() -> dict:
    """Get the accumulated token usage for the current analysis."""
    return _token_usage.copy()


def get_client() -> genai.Client | None:
    """Get a Gemini client, or None if no API key is configured."""
    if not _config.GEMINI_API_KEY:
        return None
    return genai.Client(api_key=_config.GEMINI_API_KEY)


def check_api_health() -> dict:
    """Quick health check: verify the Gemini API key works.

    Returns dict with:
        ok: True if the API responded successfully
        error: Error message if something went wrong, else None
    """
    if not _config.GEMINI_API_KEY:
        return {"ok": False, "error": "No API key configured"}

    try:
        client = genai.Client(api_key=_config.GEMINI_API_KEY)
        # Gemini 3.x Pro Preview models REQUIRE thinking mode (reject thinking_budget=0).
        # Skip the budget hint for those — let the model use its default thinking allowance.
        cfg = {
            "max_output_tokens": 4096,
            "temperature": 0,
            "response_mime_type": "application/json",
        }
        if "3." not in _config.GEMINI_MODEL and "pro" not in _config.GEMINI_MODEL.lower():
            cfg["thinking_config"] = {"thinking_budget": 0}
        response = client.models.generate_content(
            model=_config.GEMINI_MODEL,
            contents="Reply with exactly: {\"status\": \"ok\"}",
            config=cfg,
        )
        # If we got a response, the API works
        if response.text:
            return {"ok": True, "error": None}
        # Collect diagnostic info for debugging
        details = []
        if hasattr(response, "candidates") and response.candidates:
            c = response.candidates[0]
            if hasattr(c, "finish_reason"):
                details.append(f"finish_reason={c.finish_reason}")
            if hasattr(c, "safety_ratings") and c.safety_ratings:
                details.append(f"safety={c.safety_ratings}")
        detail_str = f" ({', '.join(details)})" if details else ""
        return {"ok": False, "error": f"API returned empty response{detail_str}"}
    except genai_errors.ClientError as e:
        msg = _redact(str(e))
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return {"ok": False, "error": "Rate limit exceeded — free tier (20 req/day) may be exhausted. Try again later."}
        return {"ok": False, "error": msg}
    except Exception as e:
        return {"ok": False, "error": _redact(str(e))}


def _url_slug(url: str) -> str:
    """Extract the path from a URL for easier reading."""
    try:
        return urlparse(url).path
    except Exception:
        return url


def _call_gemini(client: genai.Client, prompt: str, max_tokens: int | None = None, max_retries: int = 3) -> str:
    """Call Gemini and return the text response. Tracks token usage.

    Handles rate limits (429) with exponential backoff.
    """
    if max_tokens is None:
        max_tokens = _config.GEMINI_MAX_OUTPUT_TOKENS
    global _token_usage

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=_config.GEMINI_MODEL,
                contents=prompt,
                config={
                    "max_output_tokens": max_tokens,
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
            )

            # Track token usage
            usage = response.usage_metadata
            if usage:
                _token_usage["prompt_tokens"] += getattr(usage, "prompt_token_count", 0) or 0
                _token_usage["completion_tokens"] += getattr(usage, "candidates_token_count", 0) or 0
                _token_usage["thinking_tokens"] += getattr(usage, "thoughts_token_count", 0) or 0
                _token_usage["total_tokens"] += getattr(usage, "total_token_count", 0) or 0
            _token_usage["api_calls"] += 1

            return response.text.strip()

        except genai_errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_retries - 1:
                    wait_time = 60 * (attempt + 1)  # 60s, 120s, 180s
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(
                        f"Gemini API rate limit exceeded after {max_retries} retries. "
                        f"The free tier allows 20 requests/day for Gemini 2.5 Flash. "
                        f"Try again later or add billing to your Google AI project."
                    )
            raise

    return ""


def prepare_page_contexts(
    cleaned_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    pagerank_scores: dict[str, float],
    true_orphan_urls: set[str] | None = None,
) -> list[dict]:
    """Build structured context for pages that should be analyzed by AI.

    Selects "interesting" pages: priority URLs + top PageRank pages + orphan pages + true orphans.
    For each page, includes URL, slug, keywords, anchors, PageRank, link counts.
    """
    all_pages = set(cleaned_df["Source"].unique()) | set(cleaned_df["Destination"].unique())
    true_orphans = true_orphan_urls or set()

    # Inbound and outbound data
    inbound = cleaned_df.groupby("Destination").agg(
        inbound_count=("Source", "size"),
        inbound_anchors=("Anchor", lambda x: list(set(a for a in x if a))),
        inbound_sources=("Source", lambda x: list(set(x))),
    )
    outbound = cleaned_df.groupby("Source").agg(
        outbound_count=("Destination", "size"),
        outbound_targets=("Destination", lambda x: list(set(x))),
    )

    # Select interesting pages
    priority_urls = set(priority_df["URL"].tolist())

    # Top PageRank pages (top 50)
    sorted_pr = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)
    top_pr_urls = set(url for url, _ in sorted_pr[:50])

    # Orphan pages
    pages_with_inbound = set(inbound.index)
    orphan_urls = all_pages - pages_with_inbound

    interesting = priority_urls | top_pr_urls | orphan_urls | true_orphans
    # Also include all pages that link to or from interesting pages
    # (for better cocoon detection), but cap at 300 total
    linked_to_interesting = set()
    for url in interesting:
        if url in inbound.index:
            linked_to_interesting.update(inbound.loc[url, "inbound_sources"][:5])
        if url in outbound.index:
            linked_to_interesting.update(outbound.loc[url, "outbound_targets"][:5])

    all_interesting = interesting | linked_to_interesting
    # Cap at 500 to keep costs reasonable while covering more orphans
    max_pages = 500
    if len(all_interesting) > max_pages:
        # Prioritize: priority URLs first, then orphans + true orphans (they need links most),
        # then top PR pages, then linked neighbors
        ordered = list(priority_urls)
        ordered.extend(url for url in orphan_urls if url not in set(ordered))
        ordered.extend(url for url in true_orphans if url not in set(ordered))
        ordered.extend(url for url in top_pr_urls if url not in set(ordered))
        ordered.extend(url for url in linked_to_interesting if url not in set(ordered))
        all_interesting = set(ordered[:max_pages])

    # Build priority lookup
    priority_lookup = {}
    for _, row in priority_df.iterrows():
        priority_lookup[row["URL"]] = {
            "target_keyword": row["Target Keyword"],
            "content_type": row.get("Content Type", ""),
        }

    # Build context for each page
    contexts = []
    for url in sorted(all_interesting):
        slug = _url_slug(url)
        pr_score = pagerank_scores.get(url, 0.0)

        ctx = {
            "url": url,
            "slug": slug,
            "pagerank": round(pr_score, 8),
            "is_priority": url in priority_urls,
            "is_orphan": url in orphan_urls,
            "is_true_orphan": url in true_orphans,
        }

        # Priority info
        if url in priority_lookup:
            ctx["target_keyword"] = priority_lookup[url]["target_keyword"]
            ctx["content_type"] = priority_lookup[url]["content_type"]

        # Inbound info
        if url in inbound.index:
            row = inbound.loc[url]
            ctx["inbound_count"] = int(row["inbound_count"])
            ctx["inbound_anchors"] = row["inbound_anchors"][:10]  # Cap for prompt size
        else:
            ctx["inbound_count"] = 0
            ctx["inbound_anchors"] = []

        # Outbound info
        if url in outbound.index:
            row = outbound.loc[url]
            ctx["outbound_count"] = int(row["outbound_count"])
        else:
            ctx["outbound_count"] = 0

        contexts.append(ctx)

    return contexts


def _batch_pages(contexts: list[dict], batch_size: int = _config.AI_BATCH_SIZE) -> list[list[dict]]:
    """Split page contexts into batches."""
    return [contexts[i:i + batch_size] for i in range(0, len(contexts), batch_size)]


def detect_cocoons(
    contexts: list[dict],
    client: genai.Client,
    progress_callback=None,
) -> list[dict]:
    """Use Gemini to detect operator-based cocoons from page URLs.

    Sends URLs in batches of ~100 to avoid prompt size issues with Gemini.

    Returns a list of cocoon dicts:
    [
        {
            "operator": "bet365",
            "code_page": "https://...",
            "pages": ["https://...", ...],
        },
        ...
    ]
    """
    # Build a compact list using FULL URLs so Gemini returns full URLs
    # Prioritize: priority URLs first, then their neighbors, then the rest
    priority_contexts = [c for c in contexts if c.get("is_priority")]
    other_contexts = [c for c in contexts if not c.get("is_priority")]

    # Put priority URLs at the front so they're always in the first batch
    ordered_contexts = priority_contexts + other_contexts

    url_entries = []
    for ctx in ordered_contexts:
        entry = f"- {ctx['url']}"
        if ctx.get("target_keyword"):
            entry += f"  (keyword: {ctx['target_keyword']})"
        if ctx.get("content_type"):
            entry += f"  [type: {ctx['content_type']}]"
        url_entries.append(entry)

    # Batch URLs to avoid overloading the prompt
    batch_size = _config.AI_COCOON_BATCH_SIZE
    url_batches = [url_entries[i:i + batch_size] for i in range(0, len(url_entries), batch_size)]

    all_cocoons = []
    batch_errors = []

    for batch_idx, url_batch in enumerate(url_batches):
        if progress_callback:
            progress_callback(
                batch=batch_idx + 1,
                total_batches=len(url_batches),
                cocoons_found=len(all_cocoons),
            )

        url_text = "\n".join(url_batch)

        prompt = f"""You are an SEO analyst. I have a list of URLs from a sports betting / casino affiliate website.

Your task: detect "cocoons" — groups of pages that belong to the same betting operator (e.g., bet365, 1xbet, Betano, Caliente, etc.) — AND classify each page by type.

A cocoon typically contains:
- A **code page** (promo code / bonus page) — main conversion target
- A **review page** for the operator
- An **app page**, **streaming page**, **payment page**, **bonus page**, etc.
- Other operator-specific feature pages

Rules:
1. Group pages by operator based on URL paths and keywords.
2. Identify the **code page** for each cocoon (URL usually contains "codigo", "code", "bonus", "promo").
3. Only create a cocoon if you find at least 2 pages for an operator.
4. Pages that don't belong to any operator cocoon should be ignored.
5. **Multi-operator pages** — when a page mentions/compares MULTIPLE operators (e.g. "bet365 vs betano", "best betting sites", "top 10 betting apps", cross-brand guides, news mentioning several operators), put that page in EVERY cocoon it belongs to (same URL appears in multiple cocoons).
6. **Page types** — classify every page using ONE of these canonical types when it fits, OR a short custom type label (e.g. "esports", "horse-racing-tips") if none fits:

   Canonical types (use these when applicable):
   - Sports betting: review, code, bonus, app, streaming, payment, cashout, odds, sport-specific, customer-service, registration, comparator
   - Casino: casino-review, slots, live-casino, table-games, jackpots, casino-bonus
   - Poker: poker-review, cash-games, tournaments, freerolls
   - Other verticals: esports, virtual-sports, horse-racing, lottery, bingo, fantasy
   - Cross-cutting: vip-program, responsible-gambling, license-info, region-specific
   - Editorial/topic: topic-evergreen, topic-event-timely, topic-news, topic-tips-predictions

   "comparator" is the page type for multi-operator comparison pages.

7. IMPORTANT: Return the FULL URLs exactly as provided (starting with https://), not just paths.

Here are the URLs:

{url_text}

Respond with a JSON object with this exact structure:
{{
  "cocoons": [
    {{
      "operator": "operator name",
      "code_page": "full URL of the code page (or null if none found)",
      "pages": [
        {{"url": "full URL 1", "page_type": "review"}},
        {{"url": "full URL 2", "page_type": "code"}}
      ]
    }}
  ]
}}"""

        for attempt in range(2):  # 1 retry on failure
            try:
                text = _call_gemini(client, prompt)
                result = json.loads(text)
                batch_cocoons = result.get("cocoons", [])
                all_cocoons.extend(batch_cocoons)
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(3)
                    continue
                batch_errors.append(f"Cocoon batch {batch_idx+1}: {_redact(str(e))}")
                break

    # Merge cocoons for the same operator across batches.
    # Pages may come as plain URL strings (legacy) OR as {url, page_type} dicts (new format).
    # Normalize to a {url: page_type} mapping per cocoon, then derive `pages` (URL list) for backward compat.
    merged = {}
    for cocoon in all_cocoons:
        op = cocoon.get("operator", "").lower().strip()
        if not op:
            continue
        if op not in merged:
            merged[op] = {
                "operator": cocoon.get("operator", ""),
                "code_page": cocoon.get("code_page"),
                "page_types": {},
            }

        for page in cocoon.get("pages", []):
            if isinstance(page, dict):
                url = page.get("url")
                ptype = page.get("page_type")
            else:
                url = page
                ptype = None
            if not url:
                continue
            # Keep first non-empty page_type seen for a URL within an operator
            if url not in merged[op]["page_types"] or (ptype and not merged[op]["page_types"][url]):
                merged[op]["page_types"][url] = ptype

        if not merged[op]["code_page"] and cocoon.get("code_page"):
            merged[op]["code_page"] = cocoon["code_page"]

    # Backfill the `pages` URL list and surface multi-operator URLs for downstream rules.
    cocoons_out = []
    url_to_operators: dict[str, list[str]] = {}
    for op_key, c in merged.items():
        c["pages"] = list(c["page_types"].keys())
        cocoons_out.append(c)
        for url in c["pages"]:
            url_to_operators.setdefault(url, []).append(c["operator"])

    multi_operator_urls = {url: ops for url, ops in url_to_operators.items() if len(ops) > 1}

    # Stash on the first cocoon as a side channel — keep return signature unchanged.
    if cocoons_out:
        cocoons_out[0]["_multi_operator_urls"] = multi_operator_urls

    return cocoons_out, batch_errors


def _normalize_url(url: str) -> str:
    """Normalize a URL: strip trailing slashes (except root /)."""
    url = url.strip()
    if url.endswith("/") and url.count("/") > 3:
        url = url.rstrip("/")
    return url


def _find_closest_url(url: str, known_urls: set[str]) -> str | None:
    """Try to find a matching URL in the known set, tolerating minor AI errors.

    Checks: exact match, trailing slash variants, and substring match on the last path segment.
    """
    norm = _normalize_url(url)
    if norm in known_urls:
        return norm
    # Try with/without trailing slash
    if norm + "/" in known_urls:
        return norm + "/"
    # Try substring match on the last path segment (catches missing path prefixes)
    try:
        last_segment = urlparse(norm).path.rstrip("/").rsplit("/", 1)[-1]
        if last_segment and len(last_segment) > 10:
            matches = [u for u in known_urls if last_segment in u]
            if len(matches) == 1:
                return matches[0]
    except Exception:
        pass
    return None


def find_link_opportunities(
    contexts: list[dict],
    cocoons: list[dict],
    cleaned_df: pd.DataFrame,
    client: genai.Client,
) -> list[dict]:
    """Use Gemini to find linking opportunities and suggest anchor texts.

    Returns a list of recommendation dicts:
    [
        {
            "source_url": "...",
            "target_url": "...",
            "suggested_anchor": "...",
            "reason": "...",
            "priority": "high" | "medium" | "low",
        },
        ...
    ]
    """
    # Build cocoon lookup for context.
    # Multi-operator URLs (comparators, vs pages, cross-brand guides) belong to several cocoons.
    cocoon_info: dict[str, list[dict]] = {}
    page_type_lookup: dict[str, str] = {}
    for cocoon in cocoons:
        op = cocoon["operator"]
        code_page = cocoon.get("code_page")
        page_types = cocoon.get("page_types", {})
        for page_url in cocoon.get("pages", []):
            cocoon_info.setdefault(page_url, []).append({"operator": op, "code_page": code_page})
            ptype = page_types.get(page_url)
            if ptype and page_url not in page_type_lookup:
                page_type_lookup[page_url] = ptype

    multi_operator_urls = (cocoons[0].get("_multi_operator_urls", {}) if cocoons else {})

    # Per-URL fast lookups for the relevance scorer
    operators_for_url: dict[str, list[str]] = {
        url: [ci["operator"] for ci in cis] for url, cis in cocoon_info.items()
    }
    code_page_by_url: dict[str, str | None] = {}
    review_page_by_op: dict[str, str | None] = {}
    for cocoon in cocoons:
        op = cocoon["operator"]
        code = cocoon.get("code_page")
        for page_url in cocoon.get("pages", []):
            if page_url not in code_page_by_url:
                code_page_by_url[page_url] = code
            if cocoon.get("page_types", {}).get(page_url) == "review":
                review_page_by_op[op] = page_url
    ctx_by_url = {ctx["url"]: ctx for ctx in contexts}

    # Build existing links set for quick lookup
    existing_links = set(
        zip(cleaned_df["Source"].tolist(), cleaned_df["Destination"].tolist())
    )

    # Build known URL set for validation (all URLs from crawl + contexts)
    known_urls = set(cleaned_df["Source"].unique()) | set(cleaned_df["Destination"].unique())
    known_urls.update(ctx["url"] for ctx in contexts)

    # Split contexts into batches
    batches = _batch_pages(contexts)
    all_recommendations = []
    batch_errors = []

    for batch in batches:
        # Build context for each page in the batch
        page_descriptions = []
        for ctx in batch:
            desc = f"URL: {ctx['url']}\n"
            desc += f"  PageRank: {ctx['pagerank']}\n"
            desc += f"  Inbound links: {ctx['inbound_count']}\n"
            desc += f"  Outbound links: {ctx['outbound_count']}\n"

            if ctx.get("is_priority"):
                desc += f"  ** PRIORITY PAGE **\n"
            if ctx.get("is_orphan"):
                desc += f"  ** ORPHAN (0 inbound links) **\n"
            if ctx.get("is_true_orphan"):
                desc += f"  ** TRUE ORPHAN (not found in crawl — no links at all) **\n"
            if ctx.get("target_keyword"):
                desc += f"  Target keyword: {ctx['target_keyword']}\n"
            if ctx.get("content_type"):
                desc += f"  Content type: {ctx['content_type']}\n"
            if ctx.get("inbound_anchors"):
                anchors = ", ".join(ctx["inbound_anchors"][:5])
                desc += f"  Current inbound anchors: {anchors}\n"

            # Page type (canonical or custom)
            ptype = page_type_lookup.get(ctx["url"])
            if ptype:
                desc += f"  Page type: {ptype}\n"

            # Cocoon info — a URL may belong to several operators (multi-operator pages)
            if ctx["url"] in cocoon_info:
                cis = cocoon_info[ctx["url"]]
                if len(cis) > 1:
                    ops = ", ".join(ci["operator"] for ci in cis)
                    desc += f"  ** MULTI-OPERATOR PAGE — belongs to cocoons: {ops} ** (allowed to link to each operator)\n"
                else:
                    ci = cis[0]
                    desc += f"  Cocoon: {ci['operator']}"
                    if ci["code_page"] == ctx["url"]:
                        desc += " (THIS IS THE CODE PAGE)"
                    desc += "\n"

            page_descriptions.append(desc)

        pages_text = "\n".join(page_descriptions)

        # Build cocoon summary
        cocoon_summary = ""
        if cocoons:
            cocoon_lines = []
            for c in cocoons:
                cocoon_lines.append(
                    f"- {c['operator']}: {len(c.get('pages', []))} pages "
                    f"(code page: {c['code_page'] if c.get('code_page') else 'none'})"
                )
            cocoon_summary = "Known operator cocoons:\n" + "\n".join(cocoon_lines)

        prompt = f"""You are an SEO expert specializing in internal linking strategy for sports betting / casino affiliate sites.

I'll give you a batch of pages from a site. Your job is to find **internal linking opportunities** — pages that SHOULD link to each other but currently don't.

{cocoon_summary}

Pages in this batch:

{pages_text}

Rules for recommendations:

1. **Priority pages need more links**: Pages marked PRIORITY with few inbound links need new links pointing to them.

2. **Orphan rule (ABSOLUTE)**: Every page marked ORPHAN or TRUE ORPHAN MUST receive at least one inbound link in your recommendations. Do not skip orphan pages. An orphan page with zero inbound links gets no PageRank and is invisible — fixing this is the #1 SEO priority.

3. **Cocoon PR flow — funnel, not star**: The code page is the PageRank destination of an operator cocoon and should receive more inbound links than any other page in the silo. BUT siblings link to the code page ONLY when semantically relevant. Do NOT mechanically link every sibling to the code page. The correct pattern is a FUNNEL: content pages link to the review, the review funnels to the code page. Relevance beats mechanical linking.

4. **Multi-operator pages are allowed to link to multiple operators**:
   - Single-operator pages (e.g. "bet365 review", "betano bonus") must NEVER link to another operator's pages.
   - BUT comparator pages ("bet365 vs betano", "best betting sites", "top 10 betting apps"), cross-brand guides, and news articles that mention multiple operators belong to MULTIPLE cocoons simultaneously and SHOULD link to each relevant operator's appropriate page.

5. **Comparator topic → target page type matching** (Rule 11 in spec):
   When a comparator/multi-operator page links to an operator cocoon, match the comparator's topic to the right page type in that cocoon:
   - "Best betting sites" / listicles / "top 10" → operator's **review** or **code** page (PR-driven)
   - "vs" pages (e.g. bet365 vs betano) → operator's highest-PR sibling (usually **review**)
   - "Best betting app" / "best mobile" → operator's **app** page
   - "Best payment method" / "best crypto betting" / "best PIX" → operator's **payment method** page
   - "Best bonuses" / "welcome bonus" / "free bets" → operator's **code/bonus** page
   - "Best live betting" / "streaming" / "cashout" / "odds" → operator's matching feature page
   - "Safest" / "licensed" / "newest" / "no KYC" → operator's **review** page (trust signal)
   - "Best for [sport]" → operator's **sport-specific** page if it exists, else review
   - News/timely articles mentioning operators → operator's **review** page (never code page — informational content shouldn't force-funnel to conversion)
   - FALLBACK: when the comparator's topic doesn't match any page type in an operator's cocoon, link to the operator's **review** page.

6. **PageRank strategy**: High-PageRank pages should link to important pages that need a boost. When multiple valid sources exist for a target, prefer the source with the highest PageRank.

7. **Semantic relevance**: Only recommend links between pages that are topically related. Inside a cocoon, prefer pages in the same cluster (bonus cluster: code+bonus+registration; mobile cluster: app+streaming; money cluster: payment+cashout; betting cluster: odds+sport; trust cluster: review+customer-service).

8. **Anchor text with diversity**: Suggest natural anchors. Across multiple inbound links to the same target page, vary the anchor style with this target mix:
   - ~30% **branded** (e.g. "bet365", "bet365 sportsbook")
   - ~30% **partial-match** (e.g. "bet365 review", "bet365 rating")
   - ~20% **generic** (e.g. "read our review", "this operator", "see more")
   - ~20% **long-tail** (e.g. "our full bet365 review covering bonuses and odds")
   Never use "click here". Avoid over-optimization — do NOT use the same keyword-stuffed anchor from every source.

9. **Don't recommend links that already exist** — I've already filtered those.

10. **Use FULL URLs exactly as provided** (starting with https://), not just paths. Do NOT modify, truncate, or invent URLs.

For each recommendation, rate priority:
- **high**: Orphan/true orphan target (rule 2), or priority page with critical/low link count
- **medium**: Strengthens a cocoon (funnel pattern), boosts moderately-linked priority page, or multi-operator comparator reaching a relevant operator target
- **low**: Nice to have, semantically relevant but not urgent

Respond with a JSON object with this exact structure:
{{
  "recommendations": [
    {{
      "source_url": "full URL of the page that should ADD the link",
      "target_url": "full URL of the page being linked TO",
      "suggested_anchor": "the anchor text to use",
      "reason": "brief explanation (1-2 sentences) — mention if target is orphan/priority and why this source was chosen",
      "priority": "high"
    }}
  ]
}}

Find as many relevant opportunities as you can (aim for 5-15 per batch). ORPHANS FIRST — every orphan in the batch must appear as a target in your output."""

        for attempt in range(2):  # 1 retry on failure
            try:
                text = _call_gemini(client, prompt)
                result = json.loads(text)
                recs = result.get("recommendations", [])
                for rec in recs:
                    # Normalize URLs (strip trailing slashes)
                    src = _normalize_url(rec.get("source_url", ""))
                    tgt = _normalize_url(rec.get("target_url", ""))
                    # Validate URLs exist in known set; try to fix if not
                    src_valid = _find_closest_url(src, known_urls)
                    tgt_valid = _find_closest_url(tgt, known_urls)
                    if not src_valid or not tgt_valid:
                        continue  # Drop recommendations with unknown URLs
                    rec["source_url"] = src_valid
                    rec["target_url"] = tgt_valid
                    # Filter out self-links and already-existing links
                    if src_valid == tgt_valid:
                        continue
                    if (src_valid, tgt_valid) in existing_links:
                        continue

                    # Semantic relevance scoring (Rule 7 — hybrid hard filter + soft score)
                    src_ctx = ctx_by_url.get(src_valid)
                    tgt_ctx = ctx_by_url.get(tgt_valid)
                    src_ops = operators_for_url.get(src_valid, [])
                    tgt_ops = operators_for_url.get(tgt_valid, [])
                    is_multi_op_src = len(src_ops) > 1 or src_valid in multi_operator_urls
                    target_review = None
                    for op in tgt_ops:
                        if review_page_by_op.get(op):
                            target_review = review_page_by_op[op]
                            break
                    scored = score_pair(
                        source_url=src_valid,
                        target_url=tgt_valid,
                        source_ctx=src_ctx,
                        target_ctx=tgt_ctx,
                        source_cocoons=src_ops,
                        target_cocoons=tgt_ops,
                        source_type=page_type_lookup.get(src_valid),
                        target_type=page_type_lookup.get(tgt_valid),
                        target_code_page=code_page_by_url.get(tgt_valid),
                        target_review_page=target_review,
                        existing_links=existing_links,
                        target_keyword=(tgt_ctx.get("target_keyword") if tgt_ctx else None),
                        target_inbound_anchors=(tgt_ctx.get("inbound_anchors") if tgt_ctx else None),
                        is_multi_operator_source=is_multi_op_src,
                        target_is_past_event=is_past_event(
                            tgt_valid,
                            page_type=page_type_lookup.get(tgt_valid),
                            target_keyword=(tgt_ctx.get("target_keyword") if tgt_ctx else None),
                        ),
                    )
                    if not scored["passed"]:
                        continue
                    rec["relevance_score"] = scored["score"]
                    all_recommendations.append(rec)
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(3)
                    continue
                batch_errors.append(f"Recommendations batch: {_redact(str(e))}")
                break

    return all_recommendations, batch_errors


def run_ai_analysis(
    cleaned_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    pagerank_scores: dict[str, float],
    progress_callback=None,
    true_orphan_urls: set[str] | None = None,
) -> dict:
    """Orchestrate the full AI analysis pipeline.

    Args:
        cleaned_df: Cleaned link data.
        priority_df: Priority URLs.
        pagerank_scores: PageRank scores per URL.
        progress_callback: Optional callable(step_name, progress_fraction).
        true_orphan_urls: URLs from full site list not found in crawl (true orphans).

    Returns:
        Dictionary with:
        - "cocoons": list of cocoon dicts
        - "recommendations": list of recommendation dicts
        - "token_usage": dict with prompt_tokens, completion_tokens, thinking_tokens, total_tokens, api_calls
        - "error": error message if something went wrong, else None
    """
    client = get_client()
    if client is None:
        return {
            "cocoons": [],
            "recommendations": [],
            "token_usage": get_token_usage(),
            "error": "no_api_key",
        }

    # Reset token counter for this analysis
    reset_token_usage()

    if progress_callback:
        progress_callback(phase="preparing", fraction=0.05)

    # Prepare context
    contexts = prepare_page_contexts(cleaned_df, priority_df, pagerank_scores, true_orphan_urls)

    if not contexts:
        return {
            "cocoons": [],
            "recommendations": [],
            "token_usage": get_token_usage(),
            "error": "No pages to analyze.",
        }

    # Count total batches upfront for accurate progress
    cocoon_batch_count = max(1, (len(contexts) + _config.AI_COCOON_BATCH_SIZE - 1) // _config.AI_COCOON_BATCH_SIZE)
    rec_batches = _batch_pages(contexts)
    rec_batch_count = len(rec_batches)
    total_api_calls = cocoon_batch_count + rec_batch_count

    if progress_callback:
        progress_callback(
            phase="cocoons", fraction=0.10,
            batch=0, total_batches=cocoon_batch_count,
            cocoons_found=0, recs_found=0,
            total_api_calls=total_api_calls,
        )

    # Detect cocoons — with per-batch progress
    def cocoon_progress(batch, total_batches, cocoons_found):
        if progress_callback:
            # Cocoon phase: 0.10 to 0.35
            frac = 0.10 + 0.25 * (batch / total_batches)
            progress_callback(
                phase="cocoons", fraction=frac,
                batch=batch, total_batches=total_batches,
                cocoons_found=cocoons_found, recs_found=0,
                total_api_calls=total_api_calls,
            )

    cocoons, cocoon_errors = detect_cocoons(contexts, client, progress_callback=cocoon_progress)

    if progress_callback:
        progress_callback(
            phase="recommendations", fraction=0.35,
            batch=0, total_batches=rec_batch_count,
            cocoons_found=len(cocoons), recs_found=0,
            total_api_calls=total_api_calls,
        )

    # Find link opportunities (batched)
    recommendations = []
    all_batch_errors = list(cocoon_errors)
    for i, batch in enumerate(rec_batches):
        if progress_callback:
            # Recommendations phase: 0.35 to 0.95
            frac = 0.35 + 0.60 * ((i + 1) / rec_batch_count)
            progress_callback(
                phase="recommendations", fraction=min(frac, 0.95),
                batch=i + 1, total_batches=rec_batch_count,
                cocoons_found=len(cocoons), recs_found=len(recommendations),
                total_api_calls=total_api_calls,
            )
        batch_recs, rec_errors = find_link_opportunities(
            batch, cocoons, cleaned_df, client
        )
        recommendations.extend(batch_recs)
        all_batch_errors.extend(rec_errors)

    # Post-AI passes (Steps 6 + 7): link budgets and orphan guarantee
    page_type_lookup: dict[str, str] = {}
    for cocoon in cocoons:
        for url, ptype in cocoon.get("page_types", {}).items():
            if ptype and url not in page_type_lookup:
                page_type_lookup[url] = ptype
    contexts_by_url = {ctx["url"]: ctx for ctx in contexts}

    from src.analysis.link_budget import apply_link_budgets
    from src.analysis.orphan_guarantee import ensure_orphan_coverage

    recommendations, budget_stats = apply_link_budgets(
        recommendations, page_type_lookup, contexts_by_url
    )
    recommendations, guarantee_stats = ensure_orphan_coverage(
        recommendations, contexts, cocoons, page_type_lookup
    )

    if progress_callback:
        progress_callback(
            phase="done", fraction=1.0,
            batch=rec_batch_count, total_batches=rec_batch_count,
            cocoons_found=len(cocoons), recs_found=len(recommendations),
            total_api_calls=total_api_calls,
        )

    # Build error summary if some batches failed
    error_msg = None
    if all_batch_errors and not cocoons and not recommendations:
        error_msg = f"All AI batches failed: {all_batch_errors[0]}"
    elif all_batch_errors:
        details = "; ".join(all_batch_errors[:3])  # Show up to 3 errors
        error_msg = f"{len(all_batch_errors)} batch(es) failed after retry (partial results shown). Errors: {details}"

    return {
        "cocoons": cocoons,
        "recommendations": recommendations,
        "token_usage": get_token_usage(),
        "error": error_msg,
        "budget_stats": budget_stats,
        "guarantee_stats": guarantee_stats,
    }
