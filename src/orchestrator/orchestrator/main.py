"""Block 13 entry point.

Starts the event bus, audit pool, retrieval pool, and health server.
Registers push subscribers for Block 8 and Block 23.
Runs until interrupted.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from dotenv import load_dotenv

from . import audit, retrieval
from .bus import bus
from .events.taxonomy import ALERT_TRIGGERED, QUERY_RECEIVED, QUERY_RESPONSE
from .health import start_health_server
from .push import push_alert_to_surface, push_query_to_block8, push_response_to_surface

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def main() -> None:
    log.info("orchestrator_starting", block=13)

    # Initialise database pools
    await audit.init_pool()
    await retrieval.init_pool()

    # Register push subscribers
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=push_query_to_block8)
    bus.subscribe(QUERY_RESPONSE, block_id=23, handler=push_response_to_surface)
    bus.subscribe(ALERT_TRIGGERED, block_id=23, handler=push_alert_to_surface)

    # Start health + API server
    runner = await start_health_server()
    log.info("health_server_started", port=8080)

    log.info("orchestrator_ready")

    # Block until shutdown signal
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("orchestrator_shutting_down")
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
