"""Block 9 — Action Layer.

D-006: every irreversible action requires explicit owner confirmation.
D-025: idempotent — duplicate action_request_id is silently acknowledged.
D-026: per-conversation ordering.
D-067: every confirmation request, response, and timeout is audited.

Lifecycle:
  action.pending        → received from Block 23
  action.confirmation_requested → emitted to Block 23
  action.owner_response → received from Block 23 (confirmed or rejected)
  action.confirmed      → emitted to deletion handler (Block 15 service)
  action.rejected       → emitted to Block 23

Timeout: configurable via ACTION_TIMEOUT_SECONDS (default 120).
A background task runs every 30 seconds and rejects expired pending actions.

Surface-agnostic: Block 9 does not know about Telegram. It receives and
emits events. Block 23 manages surface-side confirmation prompts.

suppress_telegram: if True in an incoming payload, Block 9 propagates it
to all outgoing events so Block 23 can skip the Telegram send.  Used by
the E2E test suite to prevent test-generated messages reaching the owner
chat.  Production flows never set this flag.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import asyncpg
import structlog

from . import audit
from .events.schema import AlignmentResult, CLIVEEvent
from .events.taxonomy import (
    ACTION_CONFIRMATION_REQUESTED,
    ACTION_CONFIRMED,
    ACTION_REJECTED,
)

if TYPE_CHECKING:
    from .bus import EventBus

log = structlog.get_logger()

ACTION_TIMEOUT_SECONDS = int(os.environ.get("ACTION_TIMEOUT_SECONDS", "120"))

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the action layer DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, statement_cache_size=0)
    log.info("action_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Action pool not initialised — call init_pool() first")
    return _pool


async def handle_action_pending(event: CLIVEEvent) -> None:
    """Receive action.pending from Block 23, store, emit confirmation_requested.

    D-025: idempotent — if action_request_id already exists, re-emit
    confirmation_requested (Block 13 retry may redeliver).
    """
    payload = event.payload
    action_request_id_raw = payload.get("action_request_id")

    # If no action_request_id provided, generate one (new request)
    if action_request_id_raw:
        action_request_id = uuid.UUID(str(action_request_id_raw))
    else:
        action_request_id = uuid.uuid4()

    action_type = payload.get("action_type", "unknown")
    action_target = payload.get("action_target", "")
    action_description = payload.get("action_description", "")
    chat_id = int(payload.get("chat_id", 0))
    suppress_telegram = bool(payload.get("suppress_telegram", False))
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ACTION_TIMEOUT_SECONDS)

    _STANDARD_FIELDS = {
        "action_request_id", "action_type", "action_target", "action_description",
        "chat_id", "suppress_telegram", "conversation_id",
    }
    metadata = {k: v for k, v in payload.items() if k not in _STANDARD_FIELDS}

    pool = _get_pool()
    async with pool.acquire() as conn:
        # D-025: idempotent insert — if already exists, just re-send confirmation
        existing = await conn.fetchrow(
            "SELECT status FROM clive_state.pending_actions WHERE action_request_id = $1",
            action_request_id,
        )
        if existing:
            if existing["status"] != "pending":
                log.info(
                    "action_already_resolved",
                    action_request_id=str(action_request_id),
                    status=existing["status"],
                )
                return
            # Already pending — re-emit confirmation (idempotent retry)
            log.info(
                "action_pending_duplicate_resend",
                action_request_id=str(action_request_id),
            )
        else:
            await conn.execute(
                """
                INSERT INTO clive_state.pending_actions
                    (action_request_id, action_type, action_target, action_description,
                     conversation_id, chat_id, status, created_at, expires_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9)
                ON CONFLICT (action_request_id) DO NOTHING
                """,
                action_request_id,
                action_type,
                action_target,
                action_description,
                event.conversation_id,
                chat_id,
                now,
                expires_at,
                json.dumps(metadata),
            )
            log.info(
                "action_pending_stored",
                action_request_id=str(action_request_id),
                action_type=action_type,
                action_target=action_target,
            )

    # Emit action.confirmation_requested to Block 23 via bus
    # Bus module imported here to avoid circular import
    from .bus import bus as _bus  # noqa: PLC0415
    confirmation_event = CLIVEEvent(
        event_type=ACTION_CONFIRMATION_REQUESTED,
        source_block=9,
        conversation_id=event.conversation_id,
        payload={
            "action_request_id": str(action_request_id),
            "action_type": action_type,
            "action_target": action_target,
            "action_description": action_description,
            "chat_id": chat_id,
            "expires_at": expires_at.isoformat(),
            "suppress_telegram": suppress_telegram,
        },
    )
    await audit.write(confirmation_event, AlignmentResult.PASS, "emitted")
    await _bus.publish(confirmation_event)


async def handle_action_owner_response(event: CLIVEEvent) -> None:
    """Receive action.owner_response from Block 23.

    Payload must contain action_request_id and confirmed (bool).
    On confirmed=True: emit action.confirmed.
    On confirmed=False: emit action.rejected.
    On not-found or expired: emit action.rejected (safety).
    """
    payload = event.payload
    action_request_id_raw = payload.get("action_request_id")
    if not action_request_id_raw:
        log.warning("action_owner_response_missing_id")
        return

    action_request_id = uuid.UUID(str(action_request_id_raw))
    confirmed = bool(payload.get("confirmed", False))
    suppress_telegram = bool(payload.get("suppress_telegram", False))

    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT action_type, action_target, action_description,
                   conversation_id, chat_id, status, expires_at, metadata
            FROM clive_state.pending_actions
            WHERE action_request_id = $1
            """,
            action_request_id,
        )

    from .bus import bus as _bus  # noqa: PLC0415

    if not row:
        log.warning(
            "action_owner_response_not_found",
            action_request_id=str(action_request_id),
        )
        _rejection = _build_rejection_event(
            action_request_id=action_request_id,
            action_type="unknown",
            action_target="",
            reason="not_found",
            conversation_id=event.conversation_id,
            chat_id=int(payload.get("chat_id", 0)),
            suppress_telegram=suppress_telegram,
        )
        await audit.write(_rejection, AlignmentResult.PASS, "emitted")
        await _bus.publish(_rejection)
        return

    if row["status"] != "pending":
        log.info(
            "action_owner_response_already_resolved",
            action_request_id=str(action_request_id),
            status=row["status"],
        )
        return

    # Check timeout
    now = datetime.now(timezone.utc)
    if row["expires_at"] < now:
        await _resolve_action(action_request_id, "timed_out")
        _rejection = _build_rejection_event(
            action_request_id=action_request_id,
            action_type=row["action_type"],
            action_target=row["action_target"],
            reason="timed_out",
            conversation_id=event.conversation_id,
            chat_id=row["chat_id"],
            suppress_telegram=suppress_telegram,
        )
        await audit.write(_rejection, AlignmentResult.PASS, "emitted")
        await _bus.publish(_rejection)
        return

    if confirmed:
        await _resolve_action(action_request_id, "confirmed")
        stored_metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        confirmed_event = CLIVEEvent(
            event_type=ACTION_CONFIRMED,
            source_block=9,
            conversation_id=event.conversation_id,
            payload={
                "action_request_id": str(action_request_id),
                "action_type": row["action_type"],
                "action_target": row["action_target"],
                "action_description": row["action_description"],
                "chat_id": row["chat_id"],
                "suppress_telegram": suppress_telegram,
                **stored_metadata,
            },
        )
        await audit.write(confirmed_event, AlignmentResult.PASS, "emitted")
        await _bus.publish(confirmed_event)
        log.info(
            "action_confirmed",
            action_request_id=str(action_request_id),
            action_type=row["action_type"],
        )
    else:
        await _resolve_action(action_request_id, "rejected")
        rejection = _build_rejection_event(
            action_request_id=action_request_id,
            action_type=row["action_type"],
            action_target=row["action_target"],
            reason="owner_rejected",
            conversation_id=event.conversation_id,
            chat_id=row["chat_id"],
            suppress_telegram=suppress_telegram,
        )
        await audit.write(rejection, AlignmentResult.PASS, "emitted")
        await _bus.publish(rejection)
        log.info(
            "action_rejected_by_owner",
            action_request_id=str(action_request_id),
        )


async def _resolve_action(action_request_id: uuid.UUID, status: str) -> None:
    """Update pending action status and set resolved_at."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE clive_state.pending_actions
            SET status = $1, resolved_at = now()
            WHERE action_request_id = $2 AND status = 'pending'
            """,
            status,
            action_request_id,
        )


def _build_rejection_event(
    action_request_id: uuid.UUID,
    action_type: str,
    action_target: str,
    reason: str,
    conversation_id: uuid.UUID | None,
    chat_id: int,
    suppress_telegram: bool = False,
) -> CLIVEEvent:
    return CLIVEEvent(
        event_type=ACTION_REJECTED,
        source_block=9,
        conversation_id=conversation_id,
        payload={
            "action_request_id": str(action_request_id),
            "action_type": action_type,
            "action_target": action_target,
            "reason": reason,
            "chat_id": chat_id,
            "suppress_telegram": suppress_telegram,
        },
    )


async def timeout_checker(bus_instance: Any) -> None:
    """Background task: reject expired pending actions every 30 seconds.

    D-006: timeout equals rejection.
    """
    while True:
        await asyncio.sleep(30)
        try:
            pool = _get_pool()
            async with pool.acquire() as conn:
                expired_rows = await conn.fetch(
                    """
                    SELECT action_request_id, action_type, action_target,
                           conversation_id, chat_id
                    FROM clive_state.pending_actions
                    WHERE status = 'pending' AND expires_at < now()
                    """,
                )

            for row in expired_rows:
                action_request_id = row["action_request_id"]
                await _resolve_action(action_request_id, "timed_out")
                rejection = _build_rejection_event(
                    action_request_id=action_request_id,
                    action_type=row["action_type"],
                    action_target=row["action_target"],
                    reason="timed_out",
                    conversation_id=row["conversation_id"],
                    chat_id=row["chat_id"],
                    # suppress_telegram not stored in DB — timeout notifications
                    # always go to the surface (production behaviour)
                )
                await audit.write(rejection, AlignmentResult.PASS, "emitted")
                await bus_instance.publish(rejection)
                log.info(
                    "action_timed_out",
                    action_request_id=str(action_request_id),
                )
        except Exception as exc:
            log.error("timeout_checker_error", error=str(exc))
