"""Block 8 entry point.

At v0.1 Block 8 runs as a separate container. It polls Block 13
for query.received events via a subscription endpoint, or Block 13
pushes events to Block 8's HTTP intake. The exact push/pull pattern
is an implementation detail — both satisfy D-003 (no direct block
calls, Block 13 mediates).

For v0.1 simplicity: Block 13 pushes query.received events to
Block 8 via HTTP POST to /query endpoint.

v0.5: /metrics endpoint added for Prometheus scraping (D-122 Phase 2).
v0.6: DB pool initialised on startup for LLM usage tracking (D-125).
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import db as query_db
from .handler import handle_query

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def handle_query_endpoint(request: web.Request) -> web.Response:
    """Receive query.received events from Block 13."""
    event = await request.json()
    asyncio.create_task(handle_query(event))
    return web.json_response({"status": "accepted"})


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 8})


async def handle_metrics(request: web.Request) -> web.Response:  # noqa: ARG001
    """Expose Prometheus metrics for scraping (D-122 Phase 2)."""
    data = generate_latest()
    return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})


async def main() -> None:
    log.info("query_service_starting", block=8)

    # Initialise DB pool for LLM usage tracking (D-125, v0.6)
    await query_db.init_pool()

    app = web.Application()
    app.router.add_post("/query", handle_query_endpoint)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()

    log.info("query_service_ready", port=8081)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
