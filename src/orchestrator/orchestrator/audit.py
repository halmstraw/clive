"""Audit log writer for Block 16.

D-067: connects as clive_audit_writer role (INSERT-only).
D-025: idempotent — duplicate event_id is acknowledged, not duplicated.
Block 13 requirement: log write must succeed before event is dispatched.
"""

from __future__ import annotations

import hashlib
import json
import os

import asyncpg
import structlog

from .events.schema import AlignmentResult, CLIVEEvent

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the audit writer connection pool.

    Uses clive_audit_writer role — INSERT only on clive_audit.event_log.
    """
    global _pool
    dsn = (
        f"postgresql://clive_audit_writer:{os.environ['AUDIT_WRITER_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, statement_cache_size=0)
    log.info("audit_pool_initialised")


async def write(event: CLIVEEvent, alignment_result: AlignmentResult, routing_outcome: str) -> None:
    """Write event to immutable audit log.

    Must be called and awaited before dispatching the event to subscribers.
    Idempotent: duplicate event_id is silently ignored (ON CONFLICT DO NOTHING).
    """
    if _pool is None:
        raise RuntimeError("Audit pool not initialised")

    payload_hash = hashlib.sha256(
        json.dumps(event.payload, sort_keys=True).encode()
    ).hexdigest()

    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_audit.event_log
              (event_id, event_type, source_block, timestamp,
               payload_hash, alignment_result, routing_outcome,
               conversation_id, zone_scope)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.event_id,
            event.event_type,
            event.source_block,
            event.timestamp,
            payload_hash,
            alignment_result.value if hasattr(alignment_result, 'value') else alignment_result,
            routing_outcome,
            event.conversation_id,
            event.zone_scope,
        )
