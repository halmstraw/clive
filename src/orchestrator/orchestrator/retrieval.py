"""Orchestrator-mediated retrieval broker — D-043.

Block 8 does not call Block 16 directly (D-003).
Block 13 brokers the call as a synchronous sub-step within
the query.submitted event lifecycle.

At v0.1 this is a direct async function call to the storage
layer, logged but not a full event bus round-trip.

v0.3: retrieve_document_by_filename added for T8 deletion lookup (D-109).
"""

from __future__ import annotations

import os
from typing import Any
import uuid

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the retrieval connection pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    log.info("retrieval_pool_initialised")


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
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

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
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

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

    Returns {source_keys: [...], chunk_count: N}.
    If no match: source_keys = [], chunk_count = 0.
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

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

    Returns {documents: [{filename, source_key, chunk_count, ingested_at}], total: N}.
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

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
# System status — /status command (v0.4)
# ---------------------------------------------------------------------------

async def retrieve_status(zone_scope: str) -> dict[str, Any]:
    """Return system status metrics for the /status command.

    Aggregates document count, chunk count, last ingest, and last query time.
    All values are None-safe — returns gracefully with empty knowledge base.
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

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

    doc_count = int(counts["doc_count"]) if counts else 0
    chunk_count = int(counts["chunk_count"]) if counts else 0

    last_doc_name = None
    last_doc_at = None
    if last_doc and last_doc["source_key"]:
        sk = last_doc["source_key"]
        last_doc_name = sk.split("/", 1)[-1] if "/" in sk else sk
        last_doc_at = last_doc["ingested_at"].isoformat()

    last_query_at = last_query["created_at"].isoformat() if last_query else None

    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "last_doc_name": last_doc_name,
        "last_doc_at": last_doc_at,
        "last_query_at": last_query_at,
    }
