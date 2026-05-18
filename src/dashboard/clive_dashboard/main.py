"""Block 2 — Web dashboard entry point (v0.11, D-146).

Starts a FastAPI/aiohttp HTTP server serving:
  - Static dashboard UI at /
  - Auth endpoints: /auth/login, /auth/logout
  - API endpoints: /api/query, /api/response, /api/history, /api/pending,
                   /api/confirm/<id>, /api/cancel/<id>
  - Push endpoints: /push/response, /push/action-confirmation, /push/alert,
                    /push/action-outcome, /push/deletion-result

Accessible at clive.halmshaw.co.uk via Caddy (D-147 AC-2).
Auth: session token from DASHBOARD_SECRET (D-147 AC-3).
Port: 8084 (internal Docker network only; Caddy proxies externally).

v0.11 additions (D-146):
  Block 4 egress delivers QUERY_RESPONSE events here via /push/response.
  Dashboard queries carry source_surface="dashboard" so Block 4 routes
  responses back here and not to Telegram.
"""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import structlog
from aiohttp import web
from dotenv import load_dotenv

from . import auth
from .api import (
    handle_cancel,
    handle_confirm,
    handle_history,
    handle_pending,
    handle_poll_response,
    handle_query,
)
from .push import (
    handle_action_outcome_push,
    handle_alert_push,
    handle_confirmation_push,
    handle_deletion_result_push,
    handle_response_push,
)

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()

STATIC_DIR = Path(__file__).parent / "static"


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    """GET /health — health check for Docker and Caddy."""
    await asyncio.sleep(0)
    return web.json_response({"status": "ok", "block": 2, "surface": "dashboard"})


def handle_index(request: web.Request) -> web.Response:  # noqa: ARG001
    """GET / — serve the dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="Dashboard UI not found", status=404)
    return web.FileResponse(index_path)


async def main() -> None:
    log.info("dashboard_starting", block=2, port=8084)

    # Initialise DB pool for session auth (D-147 AC-3)
    await auth.init_pool()

    # Build HTTP application
    app = web.Application()

    # Health
    app.router.add_get("/health", handle_health)

    # Static files
    app.router.add_get("/", handle_index)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR, name="static")

    # Auth
    app.router.add_post("/auth/login", auth.handle_login)
    app.router.add_post("/auth/logout", auth.handle_logout)

    # Dashboard API (require session)
    app.router.add_post("/api/query", handle_query)
    app.router.add_get("/api/response", handle_poll_response)
    app.router.add_post("/api/history", handle_history)
    app.router.add_get("/api/pending", handle_pending)
    app.router.add_post("/api/confirm/{action_request_id}", handle_confirm)
    app.router.add_post("/api/cancel/{action_request_id}", handle_cancel)

    # Push endpoints — Block 13 delivers events here via Block 4 egress
    app.router.add_post("/push/response", handle_response_push)
    app.router.add_post("/push/action-confirmation", handle_confirmation_push)
    app.router.add_post("/push/action-outcome", handle_action_outcome_push)
    app.router.add_post("/push/alert", handle_alert_push)
    app.router.add_post("/push/deletion-result", handle_deletion_result_push)
    # Compatibility aliases (Block 4 uses consistent endpoint naming)
    app.router.add_post("/response", handle_response_push)
    app.router.add_post("/alert", handle_alert_push)
    app.router.add_post("/action-confirmation", handle_confirmation_push)
    app.router.add_post("/action-outcome", handle_action_outcome_push)
    app.router.add_post("/deletion-result", handle_deletion_result_push)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8084)
    await site.start()

    log.info("dashboard_started", port=8084)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("dashboard_stopping")
    await runner.cleanup()
    log.info("dashboard_stopped")


if __name__ == "__main__":
    asyncio.run(main())
