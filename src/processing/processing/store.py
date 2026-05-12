"""PostgreSQL chunk writer for Block 16 (clive_search.chunks).

Uses clive_app role (read-write on clive_search).
Idempotent: ON CONFLICT (content_hash) DO NOTHING (D-025).
"""

from __future__ import annotations

import os

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    log.info("store_pool_initialised")


async def write_chunks(
    chunks: list[str],
    embeddings: list[list[float]],
    source_key: str,
    content_hashes: list[str],
    zone_scope: str = "personal",
) -> int:
    """Insert chunks into clive_search.chunks. Returns count of rows inserted."""
    if _pool is None:
        raise RuntimeError("Store pool not initialised")

    inserted = 0
    async with _pool.acquire() as conn:
        for i, (chunk, embedding, content_hash) in enumerate(
            zip(chunks, embeddings, content_hashes)
        ):
            result = await conn.execute(
                """
                INSERT INTO clive_search.chunks
                    (content, embedding, source_attribution, zone_of_origin,
                     position, source_key, content_hash, content_tsv,
                     document_id)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7,
                     to_tsvector('english', $1),
                     gen_random_uuid())
                ON CONFLICT (content_hash) DO NOTHING
                """,
                chunk,
                embedding,
                source_key,
                zone_scope,
                i,
                source_key,
                content_hash,
            )
            if result == "INSERT 0 1":
                inserted += 1

    log.info("chunks_written", source_key=source_key, total=len(chunks), inserted=inserted)
    return inserted
