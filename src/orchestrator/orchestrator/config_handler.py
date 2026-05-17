"""Block 19 — Conversational Config execution layer (v0.12, D-149).

Handles action.confirmed events for config action types:
  config.set_spend_cap  — upsert daily_spend_cap_usd in clive_state.config
  worker.reschedule     — update cron_expression in clive_state.workers

D-006: these actions only execute after owner confirmation via Block 9 gate.
D-025: idempotent — ON CONFLICT DO UPDATE on config key is safe on re-delivery.
D-067: all config changes are recorded in clive_state.audit_log.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import structlog

from .events.schema import CLIVEEvent

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the config handler DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, statement_cache_size=0)
    log.info("config_handler_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Config handler pool not initialised — call init_pool() first")
    return _pool


async def _write_audit(
    conn: asyncpg.Connection,
    change_type: str,
    config_key: str,
    old_value: str | None,
    new_value: str,
) -> None:
    """Append a config change record to clive_state.audit_log (D-067)."""
    try:
        await conn.execute(
            """
            INSERT INTO clive_state.audit_log
                (event_id, event_type, source_block, payload)
            VALUES ($1, 'config.changed', 19, $2::jsonb)
            """,
            uuid.uuid4(),
            __import__("json").dumps({
                "change_type": change_type,
                "config_key": config_key,
                "old_value": old_value,
                "new_value": new_value,
                "changed_by": "owner",
            }),
        )
    except Exception as exc:
        log.warning("config_audit_write_failed", config_key=config_key, error=str(exc))


async def handle_config_set_spend_cap(event: CLIVEEvent) -> None:
    """Execute config.set_spend_cap after owner confirmation.

    Upserts daily_spend_cap_usd in clive_state.config and records the change
    in the audit log. Block 20 (spend cap check in Block 8) reads this key
    before falling back to the DAILY_SPEND_CAP_USD env var.

    action_target must be a parseable float string (e.g. "5.0").
    """
    payload = event.payload
    action_target = str(payload.get("action_target", ""))

    try:
        new_cap = float(action_target)
    except (TypeError, ValueError):
        log.error(
            "config_set_spend_cap_invalid_value",
            action_target=action_target,
        )
        return

    pool = _get_pool()
    async with pool.acquire() as conn:
        old_row = await conn.fetchrow(
            "SELECT config_value FROM clive_state.config WHERE config_key = 'daily_spend_cap_usd'"
        )
        old_value = old_row["config_value"] if old_row else None

        await conn.execute(
            """
            INSERT INTO clive_state.config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('daily_spend_cap_usd', $1, 'Daily LLM spend cap in USD', NOW(), 'owner')
            ON CONFLICT (config_key) DO UPDATE
                SET config_value = EXCLUDED.config_value,
                    updated_at   = NOW(),
                    updated_by   = 'owner'
            """,
            str(new_cap),
        )

        await _write_audit(conn, "spend_cap", "daily_spend_cap_usd", old_value, str(new_cap))

    log.info(
        "config_spend_cap_updated",
        old_value=old_value,
        new_value=new_cap,
    )

    from .bus import bus as _bus  # noqa: PLC0415
    from .events.schema import CLIVEEvent as _Event  # noqa: PLC0415

    await _bus.publish(_Event(
        event_type="config.changed",
        source_block=19,
        payload={
            "change_type": "spend_cap",
            "config_key": "daily_spend_cap_usd",
            "new_value": str(new_cap),
            "changed_by": "owner",
        },
    ))


async def handle_worker_reschedule(event: CLIVEEvent) -> None:
    """Execute worker.reschedule after owner confirmation.

    action_target format: "worker_name:cron_expression"
    e.g. "daily_digest:0 9 * * *"

    Updates cron_expression in clive_state.workers and records the change
    in the audit log.
    """
    payload = event.payload
    action_target = str(payload.get("action_target", ""))

    if ":" not in action_target:
        log.error("worker_reschedule_invalid_target", action_target=action_target)
        return

    worker_name, new_schedule = action_target.split(":", 1)
    worker_name = worker_name.strip()
    new_schedule = new_schedule.strip()

    if not worker_name or not new_schedule:
        log.error("worker_reschedule_empty_fields", action_target=action_target)
        return

    pool = _get_pool()
    async with pool.acquire() as conn:
        old_row = await conn.fetchrow(
            "SELECT cron_expression FROM clive_state.workers WHERE worker_name = $1",
            worker_name,
        )

        if old_row is None:
            log.warning("worker_reschedule_not_found", worker_name=worker_name)
            return

        old_schedule = old_row["cron_expression"]

        updated = await conn.fetchval(
            """
            UPDATE clive_state.workers
            SET cron_expression = $1
            WHERE worker_name = $2
            RETURNING worker_name
            """,
            new_schedule,
            worker_name,
        )

        if not updated:
            log.warning("worker_reschedule_update_failed", worker_name=worker_name)
            return

        await _write_audit(
            conn,
            "worker_schedule",
            f"workers.{worker_name}.cron_expression",
            old_schedule,
            new_schedule,
        )

    log.info(
        "worker_rescheduled",
        worker_name=worker_name,
        old_schedule=old_schedule,
        new_schedule=new_schedule,
    )

    from .bus import bus as _bus  # noqa: PLC0415
    from .events.schema import CLIVEEvent as _Event  # noqa: PLC0415

    await _bus.publish(_Event(
        event_type="config.changed",
        source_block=19,
        payload={
            "change_type": "worker_schedule",
            "worker_name": worker_name,
            "old_schedule": old_schedule,
            "new_schedule": new_schedule,
            "changed_by": "owner",
        },
    ))
