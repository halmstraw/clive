"""Block 10 — Knowledge Maintenance worker (v0.9).

Identifies stale, unaccessed knowledge chunks and presents them for
owner review via the confirmation gate. No autonomous deletion.

D-006: run() NEVER deletes chunks. It only calls request_confirmation to
       present the stale chunk list to the owner. Deletion occurs in
       handle_prune_confirmed() ONLY after explicit owner approval via
       /confirm_action.
D-003: handle_prune_confirmed() pushes to Block 23 via HTTP — no direct
       import of the Telegram library or bot API. Follows push.py pattern.
D-025: pending_actions insert uses ON CONFLICT DO NOTHING — idempotent.

Declared scope: read:storage, write:confirmations.

Threshold: KNOWLEDGE_MAINTENANCE_THRESHOLD_DAYS env var (default: 90).
Batch cap: LIMIT 5 per run. No more than five chunks presented at once.
"""

from __future__ import annotations

import datetime
import json
import os
import uuid

import asyncpg
import httpx
import structlog

from ..events.schema import CLIVEEvent

log = structlog.get_logger()

_TELEGRAM_DEFAULT_URL = "http://telegram:8082"  # NOSONAR — Docker-internal, no TLS

_pool: asyncpg.Pool | None = None


# ---------------------------------------------------------------------------
# Pool — for handle_prune_confirmed, called from main.py event dispatcher
# ---------------------------------------------------------------------------

async def init_pool() -> None:
    """Initialise the knowledge maintenance DB pool (clive_app role).

    Called from main.py alongside action.init_pool() and
    reminder_handler.init_pool(). Separate pool so this module has
    no runtime dependency on other handler pools.
    """
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, statement_cache_size=0)
    log.info("knowledge_maintenance_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Knowledge maintenance pool not initialised — call init_pool() first"
        )
    return _pool


# ---------------------------------------------------------------------------
# Worker entrypoint — called by scheduler with (run_id, pool, scoped_push)
# ---------------------------------------------------------------------------

async def run(run_id: str, pool: asyncpg.Pool, scoped_push: dict) -> str:
    """Identify stale chunks and present a confirmation request to the owner.

    D-006: this function NEVER deletes chunks. The confirmation gate (via
    scoped_push['request_confirmation']) is the only action taken. Deletion
    occurs only after the owner explicitly confirms via /confirm_action.

    If scoped_push does not contain 'request_confirmation' (scope violation),
    the worker logs a warning and returns WITHOUT presenting a confirmation.
    It does NOT fall back to direct deletion.

    Stale = retrieval_count = 0 AND created_at < NOW() - threshold_days.
    Batch is capped at LIMIT 5 per run.

    Args:
        run_id:      UUID of this worker run (from clive_state.worker_runs).
        pool:        asyncpg pool provided by the scheduler.
        scoped_push: dict of permitted push callables for this worker's scope.

    Returns:
        Human-readable outcome summary stored in worker_runs.outcome_summary.
    """
    threshold_days = int(os.environ.get("KNOWLEDGE_MAINTENANCE_THRESHOLD_DAYS", 90))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=threshold_days)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT chunk_id, source_attribution, created_at
            FROM clive_search.chunks
            WHERE retrieval_count = 0
              AND created_at < $1
            ORDER BY created_at ASC
            LIMIT 5
            """,
            cutoff,
        )

    if not rows:
        log.info("knowledge_maintenance_no_stale_chunks", threshold_days=threshold_days)
        return f"No stale chunks found (threshold: {threshold_days} days)"

    # Build the human-readable description and structured chunk list
    now = datetime.datetime.now(datetime.timezone.utc)
    chunk_list: list[dict] = []
    description_lines = [
        f"Knowledge maintenance: {len(rows)} chunk(s) not retrieved in "
        f"{threshold_days}+ days:"
    ]

    for row in rows:
        source = row["source_attribution"] or "(unknown)"
        created_at = row["created_at"]
        # asyncpg returns TIMESTAMPTZ as timezone-aware datetime; guard for naive
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        days_old = (now - created_at).days
        description_lines.append(f"  - '{source}' (ingested {days_old} days ago)")
        chunk_list.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "source": source,
                "days_old": days_old,
            }
        )

    description_lines.append("\nConfirm to delete all listed chunks. Cancel to keep them.")
    action_description = "\n".join(description_lines)

    # Present the confirmation request via the D-006 gate
    action_request_id = str(uuid.uuid4())
    chat_id = int(os.environ.get("TELEGRAM_OWNER_CHAT_ID", 0))
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    ).isoformat()

    request_confirmation = scoped_push.get("request_confirmation")
    if request_confirmation:
        await request_confirmation(
            action_type="knowledge.prune",
            action_target=json.dumps(chunk_list),
            action_description=action_description,
            chat_id=chat_id,
            expires_at=expires_at,
            action_request_id=action_request_id,
        )
    else:
        # Scope violation — log WARN, do NOT fall back to direct deletion (D-006)
        log.warning(
            "knowledge_maintenance_no_confirmation_scope",
            run_id=str(run_id),
            chunk_count=len(rows),
        )

    return f"Flagged {len(rows)} chunk(s) for review (threshold: {threshold_days} days)"


# ---------------------------------------------------------------------------
# Confirmation handler — called from main.py after owner confirms
# ---------------------------------------------------------------------------

async def handle_prune_confirmed(event: CLIVEEvent) -> None:
    """Delete confirmed stale chunks and notify the owner.

    Called by main.py's dispatch_action_confirmed when action_type is
    'knowledge.prune'. The D-006 confirmation gate has already been passed
    before this function is reached.

    D-003: notifies Block 23 via HTTP to /alert — no direct Telegram import.
           Follows the same pattern as reminder_handler._push_error.

    Args:
        event: action.confirmed event carrying action_target (JSON chunk list).
    """
    action_target = event.payload.get("action_target", "[]")
    try:
        chunks = json.loads(action_target)
    except (json.JSONDecodeError, TypeError) as exc:
        log.error(
            "knowledge_prune_invalid_action_target",
            event_id=str(event.event_id),
            error=str(exc),
        )
        return

    chunk_ids = [c["chunk_id"] for c in chunks if "chunk_id" in c]
    if not chunk_ids:
        log.warning("knowledge_prune_no_chunk_ids", event_id=str(event.event_id))
        return

    # Convert string UUIDs to uuid.UUID for the ANY($1::uuid[]) parameter
    chunk_uuids = [uuid.UUID(cid) for cid in chunk_ids]

    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM clive_search.chunks WHERE chunk_id = ANY($1::uuid[])",
            chunk_uuids,
        )

    log.info("knowledge_prune_complete", chunk_count=len(chunk_ids))

    await _push_prune_complete(len(chunk_ids))


# ---------------------------------------------------------------------------
# Alert helper — D-003 compliant; HTTP to Block 23 /alert endpoint
# ---------------------------------------------------------------------------

async def _push_prune_complete(chunk_count: int) -> None:
    """Notify the owner via Block 23 /alert after confirmed deletion.

    D-003: HTTP POST to Block 23 service URL — no direct Telegram library
    import. Follows reminder_handler._push_error pattern.

    Design choice: direct HTTP rather than constructing a CLIVEEvent and
    calling push_alert_to_surface. handle_prune_confirmed has no reference
    to the event bus and no scoped_push dict. Direct HTTP keeps the handler
    self-contained and avoids importing bus internals into worker code.
    """
    telegram_url = os.environ.get("TELEGRAM_SERVICE_URL", _TELEGRAM_DEFAULT_URL)
    message = f"Knowledge maintenance: {chunk_count} stale chunk(s) deleted."

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{telegram_url}/alert",
                json={
                    "event_id": str(uuid.uuid4()),
                    "severity": "info",
                    "title": "Knowledge maintenance complete",
                    "body": message,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
    except Exception as exc:
        log.error("knowledge_prune_alert_push_failed", error=str(exc))
