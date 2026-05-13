"""Block 15 entry point.

Receives ingest.received push events from Block 13 and processes them
in the background.  Returns 202 Accepted immediately so Block 13's
push handler does not block on processing time.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv

from . import store
from .pipeline import process

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


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


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 15})


async def main() -> None:
    log.info("processing_service_starting", block=15)

    await store.init_pool()

    app = web.Application()
    app.router.add_post("/ingest", handle_ingest)
    app.router.add_get("/health", handle_health)

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
