"""Block 9 — Web search action handler (v0.7).

Executed when action.confirmed carries action_type = "web.search".

D-006: confirmation gate already passed before this handler is called.
D-003: this handler is called by the orchestrator dispatcher; results
       are delivered to Block 23 via HTTP push (not a direct block call).

Supported providers (SEARCH_API_PROVIDER env var):
  "brave"   — Brave Search API (default)
  "serpapi" — SerpAPI

Both require SEARCH_API_KEY in /etc/clive/secrets.env.

Results are formatted as a numbered list (top 5) with title, snippet,
and URL. No LLM summarisation — the structured output is clear enough
for the owner's use.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from .events.schema import CLIVEEvent

log = structlog.get_logger()

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPAPI_URL = "https://serpapi.com/search"
MAX_RESULTS = 5


async def handle_confirmed(event: CLIVEEvent) -> None:
    """Execute a confirmed web search and push results to Block 23.

    Reads action_target (the query string) from event.payload.
    Calls the configured search provider.
    Formats top results and pushes to TELEGRAM_URL/response.
    """
    payload = event.payload
    query = payload.get("action_target", "")
    chat_id = int(payload.get("chat_id", 0))

    if not query:
        log.warning("search_handler_missing_query", event_id=str(event.event_id))
        await _push_error(chat_id, "Search failed: no query provided.")
        return

    api_key = os.environ.get("SEARCH_API_KEY", "")
    if not api_key:
        log.error("search_handler_no_api_key")
        await _push_error(chat_id, "Search not available: `SEARCH_API_KEY` not configured.")
        return

    provider = os.environ.get("SEARCH_API_PROVIDER", "brave").lower()

    try:
        results = await _call_provider(provider, query, api_key)
    except Exception as exc:
        log.error("search_api_failed", provider=provider, error=str(exc))
        await _push_error(chat_id, f"Search failed: could not reach search provider ({exc}).")
        return

    if not results:
        text = f"No results found for: {query}"
    else:
        lines = [f"Search results for: *{query}*\n"]
        for i, r in enumerate(results[:MAX_RESULTS], 1):
            title = r.get("title", "(no title)")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            lines.append(f"{i}. *{title}*")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
        text = "\n".join(lines)

    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{telegram_url}/response",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                "response_text": text,
                "confidence": {"threshold_met": True, "chunks_returned": 1},
                "chat_id": chat_id,
            },
            timeout=10.0,
        )
        resp.raise_for_status()

    log.info(
        "search_result_delivered",
        query=query,
        result_count=len(results),
        chat_id=chat_id,
    )


async def _call_provider(provider: str, query: str, api_key: str) -> list[dict[str, Any]]:
    """Call the configured search provider. Returns list of result dicts."""
    if provider == "brave":
        return await _brave_search(query, api_key)
    elif provider == "serpapi":
        return await _serpapi_search(query, api_key)
    else:
        raise ValueError(f"Unknown SEARCH_API_PROVIDER: {provider!r}")


async def _brave_search(query: str, api_key: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": MAX_RESULTS},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("web", {}).get("results", [])
    return [
        {
            "title": r.get("title", ""),
            "snippet": r.get("description", ""),
            "url": r.get("url", ""),
        }
        for r in raw
    ]


async def _serpapi_search(query: str, api_key: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            SERPAPI_URL,
            params={"q": query, "api_key": api_key, "num": MAX_RESULTS},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("organic_results", [])
    return [
        {
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
            "url": r.get("link", ""),
        }
        for r in raw
    ]


async def _push_error(chat_id: int, message: str) -> None:
    """Push an error message to the owner via Block 23."""
    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{telegram_url}/alert",
                json={"severity": "error", "title": "Search error", "body": message},
                timeout=10.0,
            )
    except Exception as exc:
        log.error("search_error_push_failed", error=str(exc))
