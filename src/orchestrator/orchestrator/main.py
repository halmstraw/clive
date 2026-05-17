"""Block 13 entry point.

Starts the event bus, audit pool, retrieval pool, action pool, and health server.
Registers push subscribers for Block 8, Block 9, Block 15, and Block 23.
Runs until interrupted.

v0.3: Block 9 (Action Layer) added — wires action event lifecycle.
v0.6: cost.cap_exceeded subscriber added (D-125, Block 20).
v0.7: action.confirmed dispatcher routes by action_type; reminder polling added.
v0.8: structlog configured for JSON output — enables Loki field extraction (D-131).
v0.8: Tool registry gate added — action.pending validated against Block 17 registry
      before dispatch to Block 9 (D-137). Admin tool enable/disable handlers wired.
v0.9: Block 10 worker scheduler added — cron-based workers via scheduler_loop (D-140).
v0.9: knowledge_maintenance worker — action.confirmed with action_type='knowledge.prune'
      routed to knowledge_maintenance.handle_prune_confirmed (D-006, D-140).
v0.12: config_handler added — action.confirmed with action_type='config.set_spend_cap'
       or 'worker.reschedule' routed to config_handler (D-149, D-006).
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
from dotenv import load_dotenv

# Configure structlog for JSON output before any loggers are created.
# JSON format enables Loki's | json parser, which powers the event bus
# Grafana dashboard (D-131). All orchestrator log lines will be JSON.
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

from . import action, audit, config_handler, registry, reminder_handler, retrieval, scheduler, search_handler
from .bus import bus
from .events.schema import CLIVEEvent
from .events.taxonomy import (
    ACTION_CONFIRMED,
    ACTION_CONFIRMATION_REQUESTED,
    ACTION_OWNER_RESPONSE,
    ACTION_PENDING,
    ACTION_REJECTED,
    ADMIN_TOOL_DISABLE,
    ADMIN_TOOL_ENABLE,
    ADMIN_TOOL_ERROR,
    ADMIN_TOOL_UPDATED,
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
    push_admin_tool_result_to_surface,
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
from .workers import knowledge_maintenance

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def dispatch_action_confirmed(event: CLIVEEvent) -> None:
    """Route action.confirmed to the correct handler based on action_type (v0.7).

    document.delete      → Block 15 deletion handler (unchanged from v0.3)
    web.search           → search_handler.handle_confirmed
    reminder.schedule    → reminder_handler.handle_confirmed
    knowledge.prune      → knowledge_maintenance.handle_prune_confirmed (v0.9)
    config.set_spend_cap → config_handler.handle_config_set_spend_cap (v0.12)
    worker.reschedule    → config_handler.handle_worker_reschedule (v0.12)
    """
    action_type = event.payload.get("action_type", "")
    if action_type == "document.delete":
        await push_confirmed_to_deletion(event)
    elif action_type == "web.search":
        await search_handler.handle_confirmed(event)
    elif action_type == "reminder.schedule":
        await reminder_handler.handle_confirmed(event)
    elif action_type == "knowledge.prune":
        await knowledge_maintenance.handle_prune_confirmed(event)
    elif action_type == "config.set_spend_cap":
        await config_handler.handle_config_set_spend_cap(event)
    elif action_type == "worker.reschedule":
        await config_handler.handle_worker_reschedule(event)
    else:
        log.warning("unhandled_action_type_on_confirmed", action_type=action_type)


async def main() -> None:
    log.info("orchestrator_starting", block=13)

    # Initialise database pools
    await audit.init_pool()
    await retrieval.init_pool()
    await action.init_pool()          # Block 9 — Action Layer (v0.3)
    await reminder_handler.init_pool()  # Block 9 — Reminder handler (v0.7)
    await scheduler.init_pool()       # Block 10 — Worker scheduler (v0.9)
    await knowledge_maintenance.init_pool()  # Block 10 — Knowledge maintenance (v0.9)
    await config_handler.init_pool()         # Block 19 — Conversational config (v0.12)

    # v0.8: bind registry gate to action pool — no new pool created (D-137).
    registry.set_pool(action._pool)

    # Register push subscribers — Block 8 query
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=push_query_to_block8)
    bus.subscribe(QUERY_RESPONSE, block_id=23, handler=push_response_to_surface)
    bus.subscribe(ALERT_TRIGGERED, block_id=23, handler=push_alert_to_surface)

    # Ingestion pipeline — Block 14 → Block 15 → Block 23 (D-099)
    bus.subscribe(INGEST_RECEIVED, block_id=15, handler=push_ingest_to_block15)
    bus.subscribe(INGEST_PROCESSED, block_id=23, handler=push_ingest_status_to_surface)
    bus.subscribe(INGEST_REJECTED, block_id=23, handler=push_ingest_status_to_surface)

    # Block 9 — Action Layer (v0.3 + v0.7, D-006)
    # v0.8: action.pending is wrapped with the tool registry gate (D-137).
    # The gate queries clive_state.tool_registry and emits action.rejected for
    # unregistered, disabled, or deprecated tools before Block 9 sees the event.
    bus.subscribe(
        ACTION_PENDING,
        block_id=9,
        handler=registry.make_gated_handler(action.handle_action_pending),
    )
    bus.subscribe(ACTION_CONFIRMATION_REQUESTED, block_id=23, handler=push_confirmation_to_surface)
    bus.subscribe(ACTION_OWNER_RESPONSE, block_id=9, handler=action.handle_action_owner_response)
    # v0.7: single dispatcher replaces direct push_confirmed_to_deletion subscription
    bus.subscribe(ACTION_CONFIRMED, block_id=9, handler=dispatch_action_confirmed)
    bus.subscribe(ACTION_REJECTED, block_id=23, handler=push_action_outcome_to_surface)
    bus.subscribe(DELETION_COMPLETE, block_id=23, handler=push_deletion_result_to_surface)
    bus.subscribe(DELETION_NOT_FOUND, block_id=23, handler=push_deletion_result_to_surface)

    # Block 20 — Cost cap notification (v0.6, D-125)
    bus.subscribe(COST_CAP_EXCEEDED, block_id=23, handler=push_cost_cap_notification_to_surface)

    # v0.8 — Block 17 / Block 19: Tool registry admin events (D-137)
    # Block 23 emits admin.tool_disable / admin.tool_enable after owner confirmation.
    # Block 13 handles them and emits admin.tool_updated / admin.tool_error.
    # Those result events are routed back to Block 23 as owner notifications.
    bus.subscribe(ADMIN_TOOL_DISABLE, block_id=13, handler=registry.handle_tool_disable)
    bus.subscribe(ADMIN_TOOL_ENABLE, block_id=13, handler=registry.handle_tool_enable)
    bus.subscribe(ADMIN_TOOL_UPDATED, block_id=23, handler=push_admin_tool_result_to_surface)
    bus.subscribe(ADMIN_TOOL_ERROR, block_id=23, handler=push_admin_tool_result_to_surface)

    # Start health + API server
    runner = await start_health_server()
    log.info("health_server_started", port=8080)

    # Background tasks
    timeout_task = asyncio.create_task(action.timeout_checker(bus))
    reminder_task = asyncio.create_task(reminder_handler.reminder_poll())  # v0.7
    scheduler_task = asyncio.create_task(scheduler.scheduler_loop())        # v0.9

    log.info("orchestrator_ready")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("orchestrator_shutting_down")
    timeout_task.cancel()
    reminder_task.cancel()
    scheduler_task.cancel()
    await asyncio.gather(timeout_task, reminder_task, scheduler_task, return_exceptions=True)
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
