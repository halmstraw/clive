"""Block 13 entry point.

Starts the event bus, audit pool, retrieval pool, action pool, and health server.
Registers push subscribers for Block 8, Block 9, Block 15, and Block 23.
Runs until interrupted.

v0.3: Block 9 (Action Layer) added — wires action event lifecycle.
v0.6: cost.cap_exceeded subscriber added (D-125, Block 20).
v0.7: action.confirmed dispatcher routes by action_type; reminder polling added.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from dotenv import load_dotenv

from . import action, audit, reminder_handler, retrieval, search_handler
from .bus import bus
from .events.schema import CLIVEEvent
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


async def dispatch_action_confirmed(event: CLIVEEvent) -> None:
    """Route action.confirmed to the correct handler based on action_type (v0.7).

    document.delete  → Block 15 deletion handler (unchanged from v0.3)
    web.search       → search_handler.handle_confirmed
    reminder.schedule → reminder_handler.handle_confirmed
    """
    action_type = event.payload.get("action_type", "")
    if action_type == "document.delete":
        await push_confirmed_to_deletion(event)
    elif action_type == "web.search":
        await search_handler.handle_confirmed(event)
    elif action_type == "reminder.schedule":
        await reminder_handler.handle_confirmed(event)
    else:
        log.warning("unhandled_action_type_on_confirmed", action_type=action_type)


async def main() -> None:
    log.info("orchestrator_starting", block=13)

    # Initialise database pools
    await audit.init_pool()
    await retrieval.init_pool()
    await action.init_pool()          # Block 9 — Action Layer (v0.3)
    await reminder_handler.init_pool()  # Block 9 — Reminder handler (v0.7)

    # Register push subscribers — Block 8 query
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=push_query_to_block8)
    bus.subscribe(QUERY_RESPONSE, block_id=23, handler=push_response_to_surface)
    bus.subscribe(ALERT_TRIGGERED, block_id=23, handler=push_alert_to_surface)

    # Ingestion pipeline — Block 14 → Block 15 → Block 23 (D-099)
    bus.subscribe(INGEST_RECEIVED, block_id=15, handler=push_ingest_to_block15)
    bus.subscribe(INGEST_PROCESSED, block_id=23, handler=push_ingest_status_to_surface)
    bus.subscribe(INGEST_REJECTED, block_id=23, handler=push_ingest_status_to_surface)

    # Block 9 — Action Layer (v0.3 + v0.7, D-006)
    bus.subscribe(ACTION_PENDING, block_id=9, handler=action.handle_action_pending)
    bus.subscribe(ACTION_CONFIRMATION_REQUESTED, block_id=23, handler=push_confirmation_to_surface)
    bus.subscribe(ACTION_OWNER_RESPONSE, block_id=9, handler=action.handle_action_owner_response)
    # v0.7: single dispatcher replaces direct push_confirmed_to_deletion subscription
    bus.subscribe(ACTION_CONFIRMED, block_id=9, handler=dispatch_action_confirmed)
    bus.subscribe(ACTION_REJECTED, block_id=23, handler=push_action_outcome_to_surface)
    bus.subscribe(DELETION_COMPLETE, block_id=23, handler=push_deletion_result_to_surface)
    bus.subscribe(DELETION_NOT_FOUND, block_id=23, handler=push_deletion_result_to_surface)

    # Block 20 — Cost cap notification (v0.6, D-125)
    bus.subscribe(COST_CAP_EXCEEDED, block_id=23, handler=push_cost_cap_notification_to_surface)

    # Start health + API server
    runner = await start_health_server()
    log.info("health_server_started", port=8080)

    # Background tasks
    timeout_task = asyncio.create_task(action.timeout_checker(bus))
    reminder_task = asyncio.create_task(reminder_handler.reminder_poll())  # v0.7

    log.info("orchestrator_ready")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("orchestrator_shutting_down")
    timeout_task.cancel()
    reminder_task.cancel()
    await asyncio.gather(timeout_task, reminder_task, return_exceptions=True)
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
