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
        response = client.models.generate_content(
            model=_config.GEMINI_MODEL,
            contents="Reply with exactly: {\"status\": \"ok\"}",
            config={
                "max_output_tokens": 256,
                "temperature": 0,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_budget": 0},
            },
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
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return {"ok": False, "error": "Rate limit exceeded — free tier (20 req/day) may be exhausted. Try again later."}
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _url_slug(url: str) -> str:
    """Extract the path from a URL for easier reading."""
    try:
        return urlparse(url).path
    except Exception:
        return url


def _call_gemini(client: genai.Client, prompt: str, max_tokens: int = 16384, max_retries: int = 3) -> str:
    """Call Gemini and return the text response. Tracks token usage.

    Handles rate limits (429) with exponential backoff.
    """
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
) -> list[dict]:
    """Build structured context for pages that should be analyzed by AI.

    Selects "interesting" pages: priority URLs + top PageRank pages + orphan pages.
    For each page, includes URL, slug, keywords, anchors, PageRank, link counts.
    """
    all_pages = set(cleaned_df["Source"].unique()) | set(cleaned_df["Destination"].unique())

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

    interesting = priority_urls | top_pr_urls | orphan_urls
    # Also include all pages that link to or from interesting pages
    # (for better cocoon detection), but cap at 300 total
    linked_to_interesting = set()
    for url in interesting:
        if url in inbound.index:
            linked_to_interesting.update(inbound.loc[url, "inbound_sources"][:5])
        if url in outbound.index:
            linked_to_interesting.update(outbound.loc[url, "outbound_targets"][:5])

    all_interesting = interesting | linked_to_interesting
    # Cap at 300 to keep costs reasonable
    if len(all_interesting) > 300:
        # Prioritize: priority URLs first, then top PR, then orphans, then linked
        ordered = list(priority_urls)
        ordered.extend(url for url in top_pr_urls if url not in priority_urls)
        ordered.extend(url for url in orphan_urls if url not in set(ordered))
        ordered.extend(url for url in linked_to_interesting if url not in set(ordered))
        all_interesting = set(ordered[:300])

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

Your task: detect "cocoons" — groups of pages that belong to the same betting operator (e.g., bet365, 1xbet, Betano, Caliente, etc.).

A cocoon typically contains:
- A **code page** (promo code / bonus page) — this is the main target page
- A **review page** for the operator
- An **app page** (mobile app review)
- **Guide pages** related to the operator
- Other pages mentioning the operator

Rules:
1. Group pages by operator based on URL paths and keywords
2. For each cocoon, identify the **code page** (usually contains "codigo", "code", "bonus", "promo" in the path)
3. Only create a cocoon if you find at least 2 pages for an operator
4. Pages that don't belong to any operator cocoon should be ignored
5. A page can only belong to ONE cocoon
6. IMPORTANT: Return the FULL URLs exactly as provided (starting with https://), not just the paths

Here are the URLs:

{url_text}

Respond with a JSON object with this exact structure:
{{
  "cocoons": [
    {{
      "operator": "operator name",
      "code_page": "full URL of the code page (or null if none found)",
      "pages": ["full URL 1", "full URL 2"]
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
                batch_errors.append(f"Cocoon batch {batch_idx+1}: {e}")
                break

    # Merge cocoons for the same operator across batches
    merged = {}
    for cocoon in all_cocoons:
        op = cocoon.get("operator", "").lower().strip()
        if op not in merged:
            merged[op] = {
                "operator": cocoon.get("operator", ""),
                "code_page": cocoon.get("code_page"),
                "pages": list(cocoon.get("pages", [])),
            }
        else:
            # Merge pages, prefer code_page if found
            merged[op]["pages"].extend(cocoon.get("pages", []))
            merged[op]["pages"] = list(set(merged[op]["pages"]))
            if not merged[op]["code_page"] and cocoon.get("code_page"):
                merged[op]["code_page"] = cocoon["code_page"]

    return list(merged.values()), batch_errors


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
    # Build cocoon lookup for context
    cocoon_info = {}
    for cocoon in cocoons:
        op = cocoon["operator"]
        code_page = cocoon.get("code_page")
        for page_url in cocoon.get("pages", []):
            cocoon_info[page_url] = {"operator": op, "code_page": code_page}

    # Build existing links set for quick lookup
    existing_links = set(
        zip(cleaned_df["Source"].tolist(), cleaned_df["Destination"].tolist())
    )

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
            if ctx.get("target_keyword"):
                desc += f"  Target keyword: {ctx['target_keyword']}\n"
            if ctx.get("content_type"):
                desc += f"  Content type: {ctx['content_type']}\n"
            if ctx.get("inbound_anchors"):
                anchors = ", ".join(ctx["inbound_anchors"][:5])
                desc += f"  Current inbound anchors: {anchors}\n"

            # Cocoon info
            if ctx["url"] in cocoon_info:
                ci = cocoon_info[ctx["url"]]
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

        prompt = f"""You are an SEO expert specializing in internal linking strategy for sports betting affiliate sites.

I'll give you a batch of pages from a site. Your job is to find **internal linking opportunities** — pages that SHOULD link to each other but currently don't.

{cocoon_summary}

Pages in this batch:

{pages_text}

Rules for recommendations:
1. **Priority pages need more links**: Pages marked PRIORITY that have few inbound links need new links pointing to them
2. **Orphan pages need links**: Pages with 0 inbound links need at least one link
3. **Cocoon strengthening**: Pages within the same operator cocoon should link to each other. The code page should receive links from all sibling pages in the cocoon
4. **PageRank strategy**: High-PageRank pages should link to important pages that need a boost
5. **Semantic relevance**: Only recommend links between pages that are topically related
6. **Anchor text**: Suggest natural, keyword-rich anchor text for each link. Use the target page's keyword when available. Avoid generic anchors like "click here"
7. **Don't recommend links that already exist** — I've already filtered those
8. **IMPORTANT**: Use the FULL URLs exactly as provided (starting with https://), not just paths

For each recommendation, rate priority:
- **high**: Priority page with critical/low link count, or orphan page, or missing cocoon code page link
- **medium**: Would strengthen a cocoon or boost a moderately-linked priority page
- **low**: Nice to have, semantically relevant but not urgent

Respond with a JSON object with this exact structure:
{{
  "recommendations": [
    {{
      "source_url": "full URL of the page that should ADD the link",
      "target_url": "full URL of the page being linked TO",
      "suggested_anchor": "the anchor text to use",
      "reason": "brief explanation (1-2 sentences)",
      "priority": "high"
    }}
  ]
}}

Find as many relevant opportunities as you can (aim for 5-15 per batch). Quality over quantity."""

        for attempt in range(2):  # 1 retry on failure
            try:
                text = _call_gemini(client, prompt)
                result = json.loads(text)
                recs = result.get("recommendations", [])
                # Filter out recommendations for links that already exist
                for rec in recs:
                    pair = (rec.get("source_url", ""), rec.get("target_url", ""))
                    if pair not in existing_links:
                        all_recommendations.append(rec)
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(3)
                    continue
                batch_errors.append(f"Recommendations batch: {e}")
                break

    return all_recommendations, batch_errors


def run_ai_analysis(
    cleaned_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    pagerank_scores: dict[str, float],
    progress_callback=None,
) -> dict:
    """Orchestrate the full AI analysis pipeline.

    Args:
        cleaned_df: Cleaned link data.
        priority_df: Priority URLs.
        pagerank_scores: PageRank scores per URL.
        progress_callback: Optional callable(step_name, progress_fraction).

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
    contexts = prepare_page_contexts(cleaned_df, priority_df, pagerank_scores)

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
    }
