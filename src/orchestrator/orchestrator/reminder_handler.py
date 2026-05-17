"""Block 9 — Reminder schedule action handler (v0.7).

Two responsibilities:

1. handle_confirmed(event) — called by the action dispatcher when
   action.confirmed carries action_type = "reminder.schedule".
   Writes a row to clive_state.scheduled_reminders.

2. reminder_poll() — long-running background coroutine, called from
   main.py alongside the existing timeout_checker task. Fires due
   reminders every 30 seconds by pushing to Block 23 via HTTP.

D-006: confirmation gate already passed before handle_confirmed is called.
D-003: fired reminders push to Block 23 via HTTP (not direct block call).
D-025: polling is idempotent — status = 'fired' prevents double-fire.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import asyncpg
import httpx
import structlog

from .events.schema import CLIVEEvent

log = structlog.get_logger()

POLL_INTERVAL = 30  # seconds
_TELEGRAM_DEFAULT_URL = "http://telegram:8082"  # NOSONAR — Docker-internal, no TLS

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the reminder DB pool (clive_app role). Called from main.py."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, statement_cache_size=0)
    log.info("reminder_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Reminder pool not initialised — call init_pool() first")
    return _pool


async def handle_confirmed(event: CLIVEEvent) -> None:
    """Store a confirmed reminder in clive_state.scheduled_reminders."""
    payload = event.payload
    chat_id = int(payload.get("chat_id", 0))
    message = payload.get("reminder_message", "")
    fire_at_iso = payload.get("fire_at", "")

    if not message or not fire_at_iso:
        log.warning(
            "reminder_handler_missing_fields",
            event_id=str(event.event_id),
            message_present=bool(message),
            fire_at_present=bool(fire_at_iso),
        )
        await _push_error("Could not schedule reminder: missing message or time.")
        return

    try:
        fire_at = datetime.fromisoformat(fire_at_iso)
    except ValueError as exc:
        log.error("reminder_invalid_fire_at", fire_at_iso=fire_at_iso, error=str(exc))
        await _push_error("Could not schedule reminder: invalid time format.")
        return

    reminder_id = uuid.uuid4()
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_state.scheduled_reminders
                (reminder_id, chat_id, message, fire_at, conversation_id, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'pending', now())
            ON CONFLICT (reminder_id) DO NOTHING
            """,
            reminder_id,
            chat_id,
            message,
            fire_at,
            event.conversation_id,
        )

    log.info(
        "reminder_stored",
        reminder_id=str(reminder_id),
        chat_id=chat_id,
        fire_at=fire_at_iso,
    )

    # Confirm to the owner (Block 23 already showed confirmation prompt;
    # this is the post-confirm acknowledgement).
    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", _TELEGRAM_DEFAULT_URL)
    display_time = fire_at.strftime("%Y-%m-%d %H:%M %Z").strip()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{telegram_url}/response",
                json={
                    "event_id": str(event.event_id),
                    "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                    "response_text": f"Reminder scheduled for {display_time}.",
                    "confidence": {"threshold_met": True, "chunks_returned": 1},
                    "chat_id": chat_id,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
    except Exception as exc:
        log.error("reminder_ack_push_failed", error=str(exc))


async def _fire_due_reminders(telegram_url: str) -> None:
    """Execute one poll iteration — exposed for testing.

    Atomically marks due reminders as 'fired' (UPDATE...RETURNING) before
    pushing to Block 23 — prevents double-fire on overlapping poll cycles.
    D-025: idempotent — status='fired' prevents re-processing.
    """
    pool = _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        due_rows = await conn.fetch(
            """
            UPDATE clive_state.scheduled_reminders
            SET status = 'fired'
            WHERE status = 'pending' AND fire_at <= $1
            RETURNING reminder_id, chat_id, message
            """,
            now,
        )

    for row in due_rows:
        reminder_id = row["reminder_id"]
        chat_id = row["chat_id"]
        message = row["message"]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{telegram_url}/response",
                    json={
                        "event_id": str(reminder_id),
                        "response_text": f"Reminder: {message}",
                        "confidence": {"threshold_met": True, "chunks_returned": 1},
                        "chat_id": chat_id,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
            log.info(
                "reminder_fired",
                reminder_id=str(reminder_id),
                chat_id=chat_id,
            )
        except Exception as exc:
            log.error(
                "reminder_fire_push_failed",
                reminder_id=str(reminder_id),
                error=str(exc),
            )


async def reminder_poll() -> None:
    """Background task: fire due reminders every POLL_INTERVAL seconds."""
    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", _TELEGRAM_DEFAULT_URL)

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            await _fire_due_reminders(telegram_url)
        except Exception as exc:
            log.error("reminder_poll_error", error=str(exc))


async def _push_error(message: str) -> None:
    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", _TELEGRAM_DEFAULT_URL)
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{telegram_url}/alert",
                json={"severity": "error", "title": "Reminder error", "body": message},
                timeout=10.0,
            )
    except Exception as exc:
        log.error("reminder_error_push_failed", error=str(exc))
