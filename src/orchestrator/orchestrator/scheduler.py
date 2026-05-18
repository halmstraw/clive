"""Block 10 — Worker scheduler (v0.9).

D-140: cron-based scheduler for Block 10 worker modules.
D-141: nine acceptance criteria for Block 10 and Block 12 delivery.

Long-running coroutine started from main.py alongside timeout_task and
reminder_task. Workers are asyncio coroutines co-located in the orchestrator
process — same pattern as reminder_handler.reminder_poll().

D-003: workers push to Block 23 via HTTP; no direct block-to-block call.
D-006: _push_worker_confirmation inserts into pending_actions and emits
       action.confirmation_requested — no worker may take destructive action
       without explicit owner confirmation.
D-025: worker_runs rows are idempotent on run_id (UUID PRIMARY KEY).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
from croniter import croniter

from .events.schema import AlignmentResult, CLIVEEvent
from .events.taxonomy import ACTION_CONFIRMATION_REQUESTED
from .metrics import worker_runs_total

log = structlog.get_logger()

SCHEDULER_TICK_SECONDS = 30

_pool: asyncpg.Pool | None = None


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------

async def init_pool() -> None:
    """Initialise the scheduler DB pool (clive_app role). Called from main.py."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, statement_cache_size=0)
    log.info("scheduler_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Scheduler pool not initialised — call init_pool() first")
    return _pool


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------

SCOPE_TO_CAPABILITY = {
    "write:telegram": "notify",
    "write:confirmations": "request_confirmation",
}


def make_scoped_push(execution_scope: list[str]) -> dict:
    """Return a dict of permitted push callables for this worker.

    Keys are capability names (str). Values are async callables.
    Workers access capabilities via scoped_push['notify'](message).
    If a key is absent, the capability is not permitted for this worker.
    Log WARN if a worker attempts to call an unlisted capability.
    """
    scoped: dict = {}
    if "write:telegram" in execution_scope:
        scoped["notify"] = _push_worker_notification
    if "write:confirmations" in execution_scope:
        scoped["request_confirmation"] = _push_worker_confirmation
    return scoped


# ---------------------------------------------------------------------------
# Push helpers — imperative HTTP calls (workers are co-located in Block 13;
# these are not CLIVEEvent-driven, but they remain D-003 compliant because
# Block 13 mediates the delivery: no worker calls Block 23 directly).
# ---------------------------------------------------------------------------

async def _push_worker_notification(message_text: str) -> None:
    """Send a worker digest/notification to Block 23 /alert endpoint."""
    import httpx  # noqa: PLC0415

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{os.environ.get('TELEGRAM_SERVICE_URL', 'http://telegram:8082')}/alert",  # NOSONAR — Docker-internal, no TLS
            json={
                "event_id": str(uuid.uuid4()),
                "severity": "info",
                "title": "Worker notification",
                "body": message_text,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def _push_worker_confirmation(
    action_type: str,
    action_target: str,
    action_description: str,
    chat_id: int,
    expires_at: str,
    action_request_id: str,
) -> None:
    """Insert pending_action row and publish confirmation request event.

    D-006: this is the confirmation gate — no worker action taken without
    explicit owner confirmation. Inserts into clive_state.pending_actions
    directly (worker is co-located in Block 13). Then publishes
    ACTION_CONFIRMATION_REQUESTED event via bus, which Block 13 routes to
    Block 23 (D-003 compliant).
    """
    action_request_uuid = uuid.UUID(str(action_request_id))
    now = datetime.now(timezone.utc)

    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_state.pending_actions
                (action_request_id, action_type, action_target, action_description,
                 conversation_id, chat_id, status, created_at, expires_at, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9)
            ON CONFLICT (action_request_id) DO NOTHING
            """,
            action_request_uuid,
            action_type,
            action_target,
            action_description,
            None,                               # workers have no conversation context
            chat_id,
            now,
            datetime.fromisoformat(expires_at),
            json.dumps({}),
        )

    # Publish action.confirmation_requested — routed to Block 23 via bus (D-003)
    from . import audit  # noqa: PLC0415
    from .bus import bus as _bus  # noqa: PLC0415

    confirmation_event = CLIVEEvent(
        event_type=ACTION_CONFIRMATION_REQUESTED,
        source_block=13,
        conversation_id=None,
        payload={
            "action_request_id": str(action_request_uuid),
            "action_type": action_type,
            "action_target": action_target,
            "action_description": action_description,
            "chat_id": chat_id,
            "expires_at": expires_at,
        },
    )
    await audit.write(confirmation_event, AlignmentResult.PASS, "emitted")
    await _bus.publish(confirmation_event)

    log.info(
        "worker_confirmation_requested",
        action_request_id=str(action_request_uuid),
        action_type=action_type,
    )


# ---------------------------------------------------------------------------
# Worker dispatch table
# ---------------------------------------------------------------------------

_WORKERS: dict[str, Any] = {}


def _load_dispatch() -> None:
    """Lazy import of worker modules to allow compilation before they exist.

    ImportError for each module is caught individually so a missing module
    does not prevent other workers from loading. Workers that fail to import
    are logged as WARN and excluded from the dispatch table — they will not
    run until the module is present and the scheduler restarts.
    """
    try:
        from .workers import daily_digest  # noqa: PLC0415
        _WORKERS["daily_digest"] = daily_digest.run
        log.info("worker_loaded", worker_name="daily_digest")
    except ImportError:
        log.warning("worker_module_not_found", worker_name="daily_digest")

    try:
        from .workers import knowledge_maintenance  # noqa: PLC0415
        _WORKERS["knowledge_maintenance"] = knowledge_maintenance.run
        log.info("worker_loaded", worker_name="knowledge_maintenance")
    except ImportError:
        log.warning("worker_module_not_found", worker_name="knowledge_maintenance")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _load_worker_configs() -> list[dict]:
    """Query workers table for all enabled cron workers.

    SELECT w.worker_name, w.cron_expression, w.execution_scope
    FROM clive_state.workers w
    JOIN clive_state.tool_registry t ON w.worker_name = t.tool_name
    WHERE w.schedule_type = 'cron' AND t.enabled = TRUE
    """
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.worker_name, w.cron_expression, w.execution_scope
            FROM clive_state.workers w
            JOIN clive_state.tool_registry t ON w.worker_name = t.tool_name
            WHERE w.schedule_type = 'cron' AND t.enabled = TRUE
            """
        )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Worker execution
# ---------------------------------------------------------------------------

async def _run_worker(worker_config: dict) -> None:
    """Execute one worker. Log run to worker_runs. Catch all exceptions.

    Steps:
    1. INSERT into clive_state.worker_runs with status='running' — record run_id.
    2. Build scoped_push from execution_scope.
    3. Call _WORKERS[worker_name](run_id, pool, scoped_push).
    4. On return: UPDATE worker_runs SET status='success'.
    5. On exception: UPDATE worker_runs SET status='error' — do NOT re-raise.
    6. Increment Prometheus counter with worker_name and outcome status.

    Scheduler must remain alive even if individual workers fail (D-025).
    """
    worker_name = worker_config["worker_name"]
    execution_scope = list(worker_config.get("execution_scope") or [])

    if worker_name not in _WORKERS:
        log.warning("worker_not_dispatched", worker_name=worker_name)
        return

    pool = _get_pool()

    # 1. Insert worker_run row with status='running', retrieve the generated run_id
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            """
            INSERT INTO clive_state.worker_runs (worker_name, status, triggered_at)
            VALUES ($1, 'running', NOW())
            RETURNING run_id
            """,
            worker_name,
        )

    log.info("worker_starting", worker_name=worker_name, run_id=str(run_id))

    # 2. Build scoped push capabilities
    scoped_push = make_scoped_push(execution_scope)

    try:
        # 3. Execute the worker
        result = await _WORKERS[worker_name](run_id, pool, scoped_push)
        outcome_summary = str(result) if result is not None else None

        # 4. Update status to 'success'
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE clive_state.worker_runs
                SET status = 'success', completed_at = NOW(), outcome_summary = $1
                WHERE run_id = $2
                """,
                outcome_summary,
                run_id,
            )

        worker_runs_total.labels(worker_name=worker_name, status="success").inc()
        log.info("worker_succeeded", worker_name=worker_name, run_id=str(run_id))

    except Exception as exc:
        # 5. Update status to 'error' — do NOT re-raise; scheduler must stay alive
        error_detail = str(exc)
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE clive_state.worker_runs
                    SET status = 'error', completed_at = NOW(), error_detail = $1
                    WHERE run_id = $2
                    """,
                    error_detail,
                    run_id,
                )
        except Exception as update_exc:
            log.error(
                "worker_run_update_failed",
                worker_name=worker_name,
                run_id=str(run_id),
                error=str(update_exc),
            )

        # 6. Increment failure counter and log
        worker_runs_total.labels(worker_name=worker_name, status="error").inc()
        log.error(
            "worker_failed",
            worker_name=worker_name,
            run_id=str(run_id),
            error=error_detail,
        )
        # Do NOT re-raise — scheduler loop must stay alive (D-025)


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

async def scheduler_loop() -> None:
    """Long-running cron scheduler. Started from main.py via create_task().

    At startup:
      - Calls _load_dispatch() to populate the worker dispatch table.
      - Loads enabled cron worker configs from DB.
      - Computes initial next_run_at for each worker using croniter.

    Loop (SCHEDULER_TICK_SECONDS sleep between iterations):
      - For each worker: if now >= next_run_at, run it and recompute next_run_at.
      - asyncio.CancelledError is caught on sleep and returns cleanly.
    """
    _load_dispatch()
    configs = await _load_worker_configs()

    # Compute initial next_run_at using naive UTC datetimes (consistent with croniter)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    schedule: dict[str, datetime] = {}
    for config in configs:
        cron = croniter(config["cron_expression"], now_utc)
        schedule[config["worker_name"]] = cron.get_next(datetime)

    log.info(
        "scheduler_started",
        worker_count=len(configs),
        workers=[c["worker_name"] for c in configs],
    )

    while True:
        try:
            await asyncio.sleep(SCHEDULER_TICK_SECONDS)
        except asyncio.CancelledError:
            log.info("scheduler_cancelled")
            raise

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        for config in configs:
            worker_name = config["worker_name"]
            next_run = schedule.get(worker_name)
            if next_run is None:
                continue

            if now_utc >= next_run:
                await _run_worker(config)
                # Recompute next_run_at from current time
                cron = croniter(
                    config["cron_expression"],
                    datetime.now(timezone.utc).replace(tzinfo=None),
                )
                schedule[worker_name] = cron.get_next(datetime)
