"""Block 4 — Interface/Egress surface routing (v0.11, D-146).

Before v0.11 Block 4 was "collapsed into Block 23" — push.py called the
Telegram URL directly. This module makes Block 4 a real distinct component.

Surface registry: maps surface names to their push endpoint base URLs.
Both Block 23 (Telegram) and Block 2 (web dashboard) receive pushes via
this module. No other file in Block 13 hardcodes surface URLs.

D-003: Block 13 (orchestrator) is the routing layer. push.py delegates
surface delivery here. No block calls another block directly.

D-147 AC-7: Surface URLs come from environment variables:
  TELEGRAM_SERVICE_URL   → Block 23 (default: http://telegram:8082)
  DASHBOARD_SERVICE_URL  → Block 2  (default: http://dashboard:8084)

Source-surface routing:
  QUERY_RESPONSE events carry source_surface in their payload.
  push_response_to_surface() routes to that surface only.
  push_to_all_surfaces() broadcasts to every registered surface —
  used for alerts and confirmation requests.

Fail behaviour:
  push_to_surface() raises on HTTP error — caller (push.py) is responsible
  for retry / dead-letter handling (D-031).
  push_to_all_surfaces() logs surface failures and continues — a degraded
  surface (e.g. dashboard down) must not block Telegram delivery.

v0.11: two surfaces registered.
"""

from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Surface registry — environment-driven, no hardcoded URLs
# ---------------------------------------------------------------------------

SURFACE_URLS: dict[str, str] = {
    "telegram": os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082"),  # NOSONAR
    "dashboard": os.environ.get("DASHBOARD_SERVICE_URL", "http://dashboard:8084"),  # NOSONAR
}


async def push_to_surface(surface: str, endpoint: str, data: dict) -> None:
    """Push data to a specific named surface.

    Args:
        surface:  Surface name (must be a key in SURFACE_URLS).
        endpoint: Path on the target surface (e.g. "/response").
        data:     JSON-serialisable payload dict.

    Raises:
        ValueError: if surface is not registered.
        httpx.HTTPStatusError: if the surface returns 4xx/5xx.
    """
    base_url = SURFACE_URLS.get(surface)
    if base_url is None:
        log.warning("egress_unknown_surface", surface=surface, endpoint=endpoint)
        raise ValueError(f"Unknown surface: {surface!r}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}{endpoint}",
            json=data,
            timeout=10.0,
        )
        resp.raise_for_status()

    log.debug("egress_push_ok", surface=surface, endpoint=endpoint)


async def push_to_all_surfaces(endpoint: str, data: dict) -> None:
    """Broadcast data to every registered surface.

    A failure on one surface is logged but does not prevent delivery to the
    others. Caller must not depend on all surfaces receiving the push.

    Args:
        endpoint: Path on all target surfaces (e.g. "/alert").
        data:     JSON-serialisable payload dict.
    """
    for surface, base_url in SURFACE_URLS.items():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}{endpoint}",
                    json=data,
                    timeout=10.0,
                )
                resp.raise_for_status()
            log.debug("egress_broadcast_ok", surface=surface, endpoint=endpoint)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "egress_broadcast_surface_failed",
                surface=surface,
                endpoint=endpoint,
                exc=str(exc),
            )
