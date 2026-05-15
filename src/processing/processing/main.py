"""Block 15 entry point.

Receives ingest.received push events from Block 13 and processes them
in the background.  Returns 202 Accepted immediately so Block 13's
push handler does not block on processing time.

v0.3: /delete endpoint added for T8 deletion pipeline.
v0.5: /metrics endpoint added for Prometheus scraping (D-122 Phase 2).
"""

from __future__ import annotations

import asyncio
import os
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import store
from .deletion import execute_deletion, init_pool as init_deletion_pool
from .pipeline import process

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")


async def handle_ingest(request: web.Request) -> web.Response:
    """Receive ingest.received event from Block 13."""
    data = await request.json()
    payload = data.get("payload", {})
    # Merge top-level fields that pipeline expects (source_key may be at top level)
    for key in ("source_key", "content_type", "conversation_id", "original_filename", "file_size", "chat_id"):
        if key in data and key not in payload:
            payload[key] = data[key]
    asyncio.create_task(process(payload))
    return web.json_response({"status": "accepted"}, status=202)


async def handle_delete(request: web.Request) -> web.Response:
    """Receive action.confirmed event from Block 13 (T8 deletion, v0.3).

    D-006: only executed after Block 9 has confirmed the action.
    D-025: idempotent — if already deleted, succeeds gracefully.
    Returns 202 immediately; deletion runs in background task.
    """
    data = await request.json()
    payload = {**data.get("payload", {}), **data}
    asyncio.create_task(execute_deletion(payload, ORCHESTRATOR_URL))
    return web.json_response({"status": "accepted"}, status=202)


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 15})


async def handle_metrics(request: web.Request) -> web.Response:  # noqa: ARG001
    """Expose Prometheus metrics for scraping (D-122 Phase 2)."""
    data = generate_latest()
    return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})


async def main() -> None:
    log.info("processing_service_starting", block=15)

    await store.init_pool()
    await init_deletion_pool()

    app = web.Application()
    app.router.add_post("/ingest", handle_ingest)
    app.router.add_post("/delete", handle_delete)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8083)
    await site.start()

    log.info("processing_service_ready", port=8083)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    await runner.cleanup()
    log.info("processing_service_stopped")


if __name__ == "__main__":
    asyncio.run(main())
