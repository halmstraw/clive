"""Block 17 Tool Registry client for Block 8 — v0.8 (D-137).

Fetches available tools from clive_state.tool_registry and caches them
with a short TTL so Block 8's system prompt always reflects the live registry
without incurring a DB round-trip on every query.

TTL strategy: 60-second in-process cache.
  Rationale: tool registry changes are operator actions (enable/disable/add),
  not high-frequency events. 60 seconds is sufficiently fresh for operational
  purposes while keeping DB load negligible.

  Cache refresh lifecycle:
    - STARTUP (main.py): registry.refresh() called eagerly so the first query
      is served from a warm cache rather than triggering a DB fetch mid-request.
    - ONGOING: get_tools() refreshes lazily when now - _cache_ts >= 60s.
    - ON ERROR: refresh() catches the exception, logs it, and retains the stale
      cache. _cache_ts is updated even on failure so we do NOT hammer the DB
      once every query during an outage — retries are spaced by the full TTL.
    - COLD START + DB UNAVAILABLE: cache stays empty; get_tools() returns [];
      Block 8 responds to action intents with "not currently available" until
      the DB is reachable.

All DB access uses the clive_app pool from db.py. No new pool is created.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from .db import get_pool

log = structlog.get_logger()

# Cache TTL — at most one DB fetch per 60 seconds per process instance.
_REGISTRY_TTL_SECONDS = 60


@dataclass
class ToolDescriptor:
    """Descriptor for a registered, enabled, non-deprecated tool.

    Fields fetched from clive_state.tool_registry.
    permission_scope is stored internally but MUST NOT be exposed to the LLM
    (D-138 AC: format tool list for LLM as tool_name + description only).
    """

    tool_name: str
    display_name: str
    description: str
    permission_scope: list[str] = field(default_factory=list)


class RegistryClient:
    """TTL-cached client for clive_state.tool_registry.

    Query: SELECT WHERE enabled = TRUE AND deprecated = FALSE.
    Cache is refreshed lazily (TTL expiry) or eagerly (via refresh()).
    On DB error: retains stale cache and logs the failure.
    """

    def __init__(self) -> None:
        self._cache: list[ToolDescriptor] = []
        # Initialise timestamp to 0.0 so the first get_tools() call always
        # triggers a refresh. time.monotonic() is used — immune to wall-clock
        # adjustments.
        self._cache_ts: float = 0.0

    async def get_tools(self) -> list[ToolDescriptor]:
        """Return cached tools, refreshing from DB if the TTL has expired.

        Block 8 runs a single asyncio event loop — no locking is required.
        Returns a snapshot copy of the cache so callers cannot mutate it.

        Returns:
            list of ToolDescriptor (enabled + non-deprecated); may be empty
            if the registry is empty or the DB is unreachable.
        """
        now = time.monotonic()
        if now - self._cache_ts >= _REGISTRY_TTL_SECONDS:
            await self.refresh()
        return list(self._cache)

    async def refresh(self) -> None:
        """Force-fetch enabled, non-deprecated tools from DB and update cache.

        Called eagerly at Block 8 startup (main.py) and lazily by get_tools()
        on TTL expiry.

        On any exception: logs the error and leaves the existing cache intact.
        _cache_ts is updated regardless so the next retry is deferred by the
        full TTL rather than retried on every query.
        """
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT tool_name,
                           display_name,
                           description,
                           permission_scope
                    FROM   clive_state.tool_registry
                    WHERE  enabled    = TRUE
                      AND  deprecated = FALSE
                    ORDER  BY tool_name
                    """
                )
            self._cache = [
                ToolDescriptor(
                    tool_name=row["tool_name"],
                    display_name=row["display_name"],
                    description=row["description"],
                    permission_scope=list(row["permission_scope"]),
                )
                for row in rows
            ]
            log.info("tool_registry_refreshed", tool_count=len(self._cache))
        except Exception as exc:
            # Retain stale cache — a transient DB error should not suddenly
            # make all tools appear unavailable to the owner.
            log.error("tool_registry_refresh_failed", error=str(exc))
        finally:
            # Always update the timestamp — prevents hammering the DB when it
            # is down by spacing retries at the full TTL interval.
            self._cache_ts = time.monotonic()


# Module-level singleton.
# Cache starts empty; first refresh triggered at startup (main.py) or on the
# first query if startup refresh was not called (e.g. in unit tests).
registry = RegistryClient()
