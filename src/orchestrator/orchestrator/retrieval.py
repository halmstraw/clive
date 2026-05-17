"""Orchestrator-mediated retrieval broker — D-043.

Block 8 does not call Block 16 directly (D-003).
Block 13 brokers the call as a synchronous sub-step within
the query.received event lifecycle.

At v0.1 this is a direct async function call to the storage
layer, logged but not a full event bus round-trip.

v0.3: retrieve_document_by_filename added for T8 deletion lookup (D-109).
v0.6: retrieve_status extended with today's LLM spend and daily cap (D-125).
v0.10: _is_valid_zone added — zone_scope validated against clive_state.zones
       before retrieval (D-143). Fail-open on DB error.
v0.12: retrieve_action_history and retrieve_workers added (D-149).
"""

from __future__ import annotations

import os
from typing import Any
import uuid

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None
_ERR_POOL_NOT_INIT = "Retrieval pool not initialised"


async def init_pool() -> None:
    """Initialise the retrieval connection pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    log.info("retrieval_pool_initialised")


async def _is_valid_zone(zone_scope: str) -> bool:
    """Check that zone_scope exists in clive_state.zones.

    D-143: zone validation before retrieval. Returns False for unknown zones.
    Non-fatal DB error: log WARN and return True (fail open — do not block
    retrieval on DB unavailability; zone boundary enforcement is best-effort
    at this layer when DB is degraded).
    """
    if _pool is None:
        return True   # pool not init'd — fail open
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM clive_state.zones WHERE zone_name = $1",
                zone_scope,
            )
        return row is not None
    except Exception as exc:  # noqa: BLE001
        log.warning("zone_validation_error", zone_scope=zone_scope, exc=str(exc))
        return True   # fail open on DB error


async def retrieve(
    retrieval_query: str,
    zone_scope: str,
    result_limit: int,
    conversation_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Retrieve relevant knowledge chunks from Block 16.

    Returns ranked_chunks list with content, source_attribution,
    relevance_score, zone_of_origin, chunk_id.

    Enforces zone boundary at query time (D-050).
    D-143: unknown zone_scope returns empty result immediately.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    if not await _is_valid_zone(zone_scope):
        log.warning(
            "retrieval_unknown_zone",
            zone_scope=zone_scope,
            conversation_id=str(conversation_id),
        )
        return {"ranked_chunks": [], "result_count": 0}

    log.info(
        "retrieval_start",
        conversation_id=str(conversation_id),
        zone_scope=zone_scope,
        result_limit=result_limit,
    )

    async with _pool.acquire() as conn:
        # Hybrid retrieval: full-text search + vector similarity
        # Reranking applied in application code after initial fetch
        rows = await conn.fetch(
            """
            SELECT * FROM (
                SELECT
                    chunk_id,
                    content,
                    source_attribution,
                    zone_of_origin,
                    ts_rank_cd(
                        to_tsvector('english', content),
                        plainto_tsquery('english', $1)
                    ) AS text_score,
                    COALESCE(
                        1 - (embedding <=> (
                            SELECT embedding FROM clive_search.chunks
                            WHERE content = $1 LIMIT 1
                        )),
                        0.0
                    ) AS vector_score
                FROM clive_search.chunks
                WHERE zone_of_origin = $2
            ) ranked
            ORDER BY text_score + vector_score DESC
            LIMIT $3
            """,
            retrieval_query,
            zone_scope,
            result_limit,
        )

    ranked_chunks = [
        {
            "chunk_id": str(row["chunk_id"]),
            "content": row["content"],
            "source_attribution": row["source_attribution"],
            "relevance_score": float(row["text_score"] + row["vector_score"]),
            "zone_of_origin": row["zone_of_origin"],
        }
        for row in rows
    ]

    log.info(
        "retrieval_complete",
        conversation_id=str(conversation_id),
        result_count=len(ranked_chunks),
    )

    return {"ranked_chunks": ranked_chunks, "result_count": len(ranked_chunks)}


async def retrieve_system_document(
    document_type: str,
    zone_scope: str,
    version_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve a system document (personality or alignment rules) by identity.

    Returns full document content, version_id, timestamp, is_active.
    Note: zone_scope validation is NOT applied here — system documents are
    not per-user data; Block 16 validates by document_type and is_active.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    async with _pool.acquire() as conn:
        if version_id:
            row = await conn.fetchrow(
                """
                SELECT document_content, version_id, created_at, is_active
                FROM clive_state.system_documents
                WHERE document_type = $1 AND version_id = $2 AND zone_scope = $3
                """,
                document_type, version_id, zone_scope,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT document_content, version_id, created_at, is_active
                FROM clive_state.system_documents
                WHERE document_type = $1 AND is_active = true AND zone_scope = $2
                """,
                document_type, zone_scope,
            )

    if not row:
        raise ValueError(f"System document not found: {document_type}")

    return {
        "document_content": row["document_content"],
        "version_id": str(row["version_id"]),
        "version_timestamp": row["created_at"].isoformat(),
        "is_active": row["is_active"],
    }


async def retrieve_document_by_filename(
    filename: str,
    zone_scope: str,
) -> dict[str, Any]:
    """Look up all source_keys matching a given filename in Block 16.

    D-109: source_key format is {uuid}/{original_filename}.
    Matches WHERE source_key LIKE '%/' || filename.
    D-143: unknown zone_scope returns empty result immediately.

    Returns {source_keys: [...], chunk_count: N}.
    If no match: source_keys = [], chunk_count = 0.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    if not await _is_valid_zone(zone_scope):
        log.warning("retrieval_unknown_zone", zone_scope=zone_scope)
        return {"source_keys": [], "chunk_count": 0}

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source_key, count(*) AS chunk_count
            FROM clive_search.chunks
            WHERE source_key LIKE '%/' || $1
            AND zone_of_origin = $2
            GROUP BY source_key
            """,
            filename,
            zone_scope,
        )

    if not rows:
        return {"source_keys": [], "chunk_count": 0}

    source_keys = [row["source_key"] for row in rows]
    total_chunks = sum(int(row["chunk_count"]) for row in rows)

    log.info(
        "document_lookup_by_filename",
        filename=filename,
        source_keys_count=len(source_keys),
        total_chunks=total_chunks,
    )

    return {"source_keys": source_keys, "chunk_count": total_chunks}


async def retrieve_document_list(
    zone_scope: str,
    limit: int = 25,
) -> dict[str, Any]:
    """Return ingested documents with chunk counts and ingest dates (v0.4 /list).

    source_key format is {uuid}/{original_filename} — strips UUID prefix
    to return the original filename for display.
    D-143: unknown zone_scope returns empty result immediately.

    Returns {documents: [{filename, source_key, chunk_count, ingested_at}], total: N}.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    if not await _is_valid_zone(zone_scope):
        log.warning("retrieval_unknown_zone", zone_scope=zone_scope)
        return {"documents": [], "total": 0}

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source_key,
                   count(*)        AS chunk_count,
                   max(created_at) AS ingested_at
            FROM clive_search.chunks
            WHERE zone_of_origin = $1
            GROUP BY source_key
            ORDER BY max(created_at) DESC
            LIMIT $2
            """,
            zone_scope,
            limit,
        )

    documents = []
    for row in rows:
        source_key = row["source_key"]
        filename = source_key.split("/", 1)[-1] if "/" in source_key else source_key
        documents.append({
            "filename": filename,
            "source_key": source_key,
            "chunk_count": int(row["chunk_count"]),
            "ingested_at": row["ingested_at"].isoformat(),
        })

    log.info("document_list_retrieved", zone_scope=zone_scope, total=len(documents))
    return {"documents": documents, "total": len(documents)}


# ---------------------------------------------------------------------------
# Block 11 — Conversation memory (v0.4, D-115)
# ---------------------------------------------------------------------------

CONVERSATION_HISTORY_LIMIT = int(
    __import__("os").environ.get("CONVERSATION_HISTORY_LIMIT", "10")
)


async def get_conversation_history(
    conversation_id: uuid.UUID,
    limit: int | None = None,
) -> list[dict[str, str]]:
    """Return recent conversation turns for a conversation, oldest first.

    D-115: Block 13 mediates memory reads. Returns [] if pool not ready
    (non-fatal — query proceeds without history).
    """
    if _pool is None:
        return []

    effective_limit = limit if limit is not None else CONVERSATION_HISTORY_LIMIT

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content
            FROM clive_state.conversation_turns
            WHERE conversation_id = $1
            ORDER BY turn_number DESC
            LIMIT $2
            """,
            conversation_id,
            effective_limit,
        )

    # Reverse so history is oldest-first (chronological for LLM prompt)
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


async def store_conversation_turn(
    event_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
) -> None:
    """Store a conversation turn. Idempotent on (event_id, role).

    D-025: ON CONFLICT DO NOTHING ensures at-least-once delivery is safe.
    turn_number is auto-assigned as MAX(turn_number)+1 within the conversation.
    """
    if _pool is None:
        return

    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_state.conversation_turns
                (event_id, conversation_id, turn_number, role, content)
            SELECT $1, $2,
                   COALESCE((
                       SELECT MAX(turn_number)
                       FROM clive_state.conversation_turns
                       WHERE conversation_id = $2
                   ), 0) + 1,
                   $3, $4
            ON CONFLICT (event_id, role) DO NOTHING
            """,
            event_id,
            conversation_id,
            role,
            content,
        )


# ---------------------------------------------------------------------------
# System status — /status command (v0.4, extended v0.6)
# ---------------------------------------------------------------------------

async def retrieve_status(zone_scope: str) -> dict[str, Any]:
    """Return system status metrics for the /status command.

    Aggregates document count, chunk count, last ingest, last query time,
    and today's LLM spend (D-125, v0.6).

    All values are None-safe — returns gracefully with empty knowledge base
    or empty llm_usage table.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    async with _pool.acquire() as conn:
        counts = await conn.fetchrow(
            """
            SELECT count(DISTINCT source_key) AS doc_count,
                   count(*)                   AS chunk_count
            FROM clive_search.chunks
            WHERE zone_of_origin = $1
            """,
            zone_scope,
        )

        last_doc = await conn.fetchrow(
            """
            SELECT source_key, max(created_at) AS ingested_at
            FROM clive_search.chunks
            WHERE zone_of_origin = $1
            GROUP BY source_key
            ORDER BY max(created_at) DESC
            LIMIT 1
            """,
            zone_scope,
        )

        last_query = await conn.fetchrow(
            """
            SELECT created_at
            FROM clive_state.conversation_turns
            WHERE role = 'user'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )

        # Block 20 — today's LLM spend (D-125, v0.6)
        spend_row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(cost_usd), 0.0) AS total_spend
            FROM clive_state.llm_usage
            WHERE created_at >= CURRENT_DATE
            """
        )

    doc_count = int(counts["doc_count"]) if counts else 0
    chunk_count = int(counts["chunk_count"]) if counts else 0

    last_doc_name = None
    last_doc_at = None
    if last_doc and last_doc["source_key"]:
        sk = last_doc["source_key"]
        last_doc_name = sk.split("/", 1)[-1] if "/" in sk else sk
        last_doc_at = last_doc["ingested_at"].isoformat()

    last_query_at = last_query["created_at"].isoformat() if last_query else None

    # Block 20 — today's spend and configured cap
    llm_spend_today_usd = float(spend_row["total_spend"]) if spend_row else 0.0
    daily_cap_str = os.environ.get("DAILY_SPEND_CAP_USD", "").strip()
    daily_cap_usd: float | None = None
    if daily_cap_str:
        try:
            daily_cap_usd = float(daily_cap_str)
        except ValueError:
            pass

    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "last_doc_name": last_doc_name,
        "last_doc_at": last_doc_at,
        "last_query_at": last_query_at,
        "llm_spend_today_usd": llm_spend_today_usd,
        "daily_cap_usd": daily_cap_usd,
    }

# ---------------------------------------------------------------------------
# Block 5 / Block 2 — Dashboard API retrieval (v0.11, D-146)
# ---------------------------------------------------------------------------

async def get_pending_actions(zone_scope: str) -> list[dict[str, Any]]:
    """Return pending (unresolved) actions for the dashboard display.

    D-147 AC-5: dashboard /api/pending reads this endpoint via Block 13's
    /retrieve/pending-actions HTTP route. Only status='pending' rows are
    returned — expired rows are cleaned up by the timeout_checker background
    task in action.py.

    Returns list of dicts with action_request_id, action_type, action_target,
    action_description, conversation_id, expires_at, zone_scope, created_at.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action_request_id, action_type, action_target,
                   action_description, conversation_id, expires_at,
                   zone_scope, created_at
            FROM clive_state.pending_actions
            WHERE status = 'pending'
              AND zone_scope = $1
              AND expires_at > NOW()
            ORDER BY created_at DESC
            """,
            zone_scope,
        )

    actions = [
        {
            "action_request_id": str(row["action_request_id"]),
            "action_type": row["action_type"],
            "action_target": row["action_target"],
            "action_description": row["action_description"],
            "conversation_id": str(row["conversation_id"]) if row["conversation_id"] else None,
            "expires_at": row["expires_at"].isoformat(),
            "zone_scope": row["zone_scope"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]

    log.info("pending_actions_retrieved", zone_scope=zone_scope, count=len(actions))
    return actions


# ---------------------------------------------------------------------------
# v0.12 — Self-knowledge retrieval (D-149)
# ---------------------------------------------------------------------------

async def retrieve_action_history(
    zone_scope: str,
    days: int = 7,
) -> dict[str, Any]:
    """Return resolved actions from the last N days for a given zone.

    D-143: unknown zone_scope returns empty result immediately.
    Queries clive_state.pending_actions ordered newest-first; capped at 50 rows.

    Returns {actions: [...], total: N, days: N}.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    if not await _is_valid_zone(zone_scope):
        log.warning("retrieval_unknown_zone", zone_scope=zone_scope)
        return {"actions": [], "total": 0, "days": days}

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action_request_id, action_type, action_target,
                   action_description, status, created_at, zone_scope
            FROM clive_state.pending_actions
            WHERE zone_scope = $1
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
            ORDER BY created_at DESC
            LIMIT 50
            """,
            zone_scope,
            str(days),
        )

    actions = [
        {
            "action_request_id": str(row["action_request_id"]),
            "action_type": row["action_type"],
            "action_target": row["action_target"],
            "action_description": row["action_description"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat(),
            "zone_scope": row["zone_scope"],
        }
        for row in rows
    ]

    log.info(
        "action_history_retrieved",
        zone_scope=zone_scope,
        days=days,
        total=len(actions),
    )
    return {"actions": actions, "total": len(actions), "days": days}


async def retrieve_workers() -> dict[str, Any]:
    """Return registered workers with schedule and health information.

    JOINs clive_state.workers (schedule) with clive_state.tool_registry
    (display_name, description, enabled, health_status).

    Returns {workers: [...], total: N}.
    """
    if _pool is None:
        raise RuntimeError(_ERR_POOL_NOT_INIT)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                w.worker_name,
                t.display_name,
                t.description,
                t.enabled,
                t.health_status,
                w.schedule_type,
                w.cron_expression,
                w.last_run_at,
                w.next_run_at
            FROM clive_state.workers w
            JOIN clive_state.tool_registry t ON t.tool_name = w.worker_name
            ORDER BY w.worker_name
            """
        )

    workers = [
        {
            "tool_name": row["worker_name"],
            "display_name": row["display_name"],
            "description": row["description"],
            "enabled": row["enabled"],
            "health_status": row["health_status"],
            "schedule_type": row["schedule_type"],
            "schedule": row["cron_expression"],
            "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
            "next_run_at": row["next_run_at"].isoformat() if row["next_run_at"] else None,
        }
        for row in rows
    ]

    log.info("workers_retrieved", total=len(workers))
    return {"workers": workers, "total": len(workers)}
