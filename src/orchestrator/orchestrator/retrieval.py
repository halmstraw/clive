"""Orchestrator-mediated retrieval broker — D-043.

Block 8 does not call Block 16 directly (D-003).
Block 13 brokers the call as a synchronous sub-step within
the query.submitted event lifecycle.

At v0.1 this is a direct async function call to the storage
layer, logged but not a full event bus round-trip.
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
