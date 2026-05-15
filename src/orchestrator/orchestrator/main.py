"""Block 13 entry point.

Starts the event bus, audit pool, retrieval pool, action pool, and health server.
Registers push subscribers for Block 8, Block 9, Block 15, and Block 23.
Runs until interrupted.

v0.3: Block 9 (Action Layer) added — wires action event lifecycle.
v0.6: cost.cap_exceeded subscriber added (D-125, Block 20).
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from dotenv import load_dotenv

from . import action, audit, retrieval
from .bus import bus
from .events.taxonomy import (
    ACTION_CONFIRMED,
    ACTION_CONFIRMATION_REQUESTED,
    ACTION_OWNER_RESPONSE,
    ACTION_PENDING,
    ACTION_REJECTED,
    ALERT_TRIGGERED,
    COST_CAP_EXCEEDED,
    DELETION_COMPLETE,
    DELETION_NOT_FOUND,
    INGEST_PROCESSED,
    INGEST_RECEIVED,
    INGEST_REJECTED,
    QUERY_RECEIVED,
    QUERY_RESPONSE,
)
from .health import start_health_server
from .push import (
    push_action_outcome_to_surface,
    push_alert_to_surface,
    push_confirmed_to_deletion,
    push_confirmation_to_surface,
    push_cost_cap_notification_to_surface,
    push_deletion_result_to_surface,
    push_ingest_status_to_surface,
    push_ingest_to_block15,
    push_query_to_block8,
    push_response_to_surface,
)

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def main() -> None:
    log.info("orchestrator_starting", block=13)

    # Initialise database pools
    await audit.init_pool()
    await retrieval.init_pool()
    await action.init_pool()  # Block 9 — Action Layer (v0.3)

    # Register push subscribers — Block 8 query
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=push_query_to_block8)
    bus.subscribe(QUERY_RESPONSE, block_id=23, handler=push_response_to_surface)
    bus.subscribe(ALERT_TRIGGERED, block_id=23, handler=push_alert_to_surface)

    # Ingestion pipeline — Block 14 → Block 15 → Block 23 (D-099)
    bus.subscribe(INGEST_RECEIVED, block_id=15, handler=push_ingest_to_block15)
    bus.subscribe(INGEST_PROCESSED, block_id=23, handler=push_ingest_status_to_surface)
    bus.subscribe(INGEST_REJECTED, block_id=23, handler=push_ingest_status_to_surface)

    # Block 9 — Action Layer (v0.3, D-006)
    # action.pending → Block 9 handler (stores state, emits confirmation_requested)
    bus.subscribe(ACTION_PENDING, block_id=9, handler=action.handle_action_pending)
    # action.confirmation_requested → Block 23 (prompts owner)
    bus.subscribe(ACTION_CONFIRMATION_REQUESTED, block_id=23, handler=push_confirmation_to_surface)
    # action.owner_response → Block 9 handler (resolves: confirmed or rejected)
    bus.subscribe(ACTION_OWNER_RESPONSE, block_id=9, handler=action.handle_action_owner_response)
    # action.confirmed → Block 15 deletion handler
    bus.subscribe(ACTION_CONFIRMED, block_id=15, handler=push_confirmed_to_deletion)
    # action.rejected → Block 23 (notifies owner)
    bus.subscribe(ACTION_REJECTED, block_id=23, handler=push_action_outcome_to_surface)
    # deletion results → Block 23
    bus.subscribe(DELETION_COMPLETE, block_id=23, handler=push_deletion_result_to_surface)
    bus.subscribe(DELETION_NOT_FOUND, block_id=23, handler=push_deletion_result_to_surface)

    # Block 20 — Cost cap notification (v0.6, D-125)
    # cost.cap_exceeded emitted by Block 8 → owner alert via Block 23
    bus.subscribe(COST_CAP_EXCEEDED, block_id=23, handler=push_cost_cap_notification_to_surface)

    # Start health + API server
    runner = await start_health_server()
    log.info("health_server_started", port=8080)

    # Block 9 — timeout checker background task (D-006: timeout = rejection)
    timeout_task = asyncio.create_task(action.timeout_checker(bus))

    log.info("orchestrator_ready")

    # Block until shutdown signal
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("orchestrator_shutting_down")
    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
