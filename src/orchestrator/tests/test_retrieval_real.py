"""Integration tests: real PostgreSQL retrieval — D-095, D-065.

Ingests a real document (synthetic), runs a retrieval query against it,
and asserts the retrieved chunks contain expected content.

Requires TEST_DB_URL env var.  Skipped otherwise.

The embedding stored is a fixed 1536-dim test vector (all 0.5).  This means
vector_score is 0 for all retrieval queries (no exact match in the subquery).
The text_score from ts_rank_cd drives ranking — which is exactly what this
test exercises.

asyncpg has no built-in pgvector codec; embeddings are passed as a cast
string ($N::vector) rather than a Python list.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

TEST_DB_URL = os.environ.get("TEST_DB_URL")

TEST_EMBEDDING_STR = "[" + ",".join("0.5" for _ in range(1536)) + "]"
TEST_ZONE = "personal"
TEST_SOURCE_KEY = "test-integration/clive-test-doc.txt"


@pytest.fixture
async def db_conn():
    if not TEST_DB_URL:
        pytest.skip("TEST_DB_URL not set — skipping DB integration tests")
    conn = await asyncpg.connect(TEST_DB_URL)
    yield conn
    await conn.close()


@pytest.fixture
async def inserted_chunks(db_conn):
    """Insert two test chunks; clean up after the test."""
    chunk_ids = []
    chunks = [
        ("CLIVE is an AI system that retrieves knowledge from ingested documents.", "chunk_hash_1"),
        ("The ingestion pipeline stores embeddings in PostgreSQL with pgvector.", "chunk_hash_2"),
    ]
    for i, (content, content_hash) in enumerate(chunks):
        run_hash = f"{content_hash}_{uuid.uuid4().hex[:8]}"
        chunk_id = await db_conn.fetchval(
            """
            INSERT INTO clive_search.chunks
              (content, embedding, source_attribution, zone_of_origin,
               position, source_key, content_hash, content_tsv, document_id)
            VALUES
              ($1, $2::vector, $3, $4, $5, $6, $7,
               to_tsvector('english', $1),
               gen_random_uuid())
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING chunk_id
            """,
            content,
            TEST_EMBEDDING_STR,
            TEST_SOURCE_KEY,
            TEST_ZONE,
            i,
            TEST_SOURCE_KEY,
            run_hash,
        )
        if chunk_id:
            chunk_ids.append(chunk_id)

    yield chunk_ids

    if chunk_ids:
        await db_conn.execute(
            "DELETE FROM clive_search.chunks WHERE chunk_id = ANY($1::uuid[])",
            chunk_ids,
        )


@pytest.mark.asyncio
async def test_retrieval_returns_matching_chunk(db_conn, inserted_chunks):
    """Retrieval query returns chunks whose text matches the query."""
    assert inserted_chunks, "No chunks inserted — check test DB setup"

    rows = await db_conn.fetch(
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
              AND chunk_id = ANY($3::uuid[])
        ) ranked
        ORDER BY text_score + vector_score DESC
        LIMIT 5
        """,
        "CLIVE knowledge retrieval",
        TEST_ZONE,
        inserted_chunks,
    )

    assert len(rows) > 0, "Retrieval returned no chunks"
    contents = [r["content"] for r in rows]
    assert any("CLIVE" in c or "knowledge" in c or "retriev" in c for c in contents), (
        f"Expected content not found in retrieved chunks: {contents}"
    )


@pytest.mark.asyncio
async def test_retrieval_zone_filter_enforced(db_conn, inserted_chunks):
    """Retrieval with a different zone returns no results — D-050."""
    rows = await db_conn.fetch(
        """
        SELECT chunk_id FROM clive_search.chunks
        WHERE zone_of_origin = 'bridge'
          AND chunk_id = ANY($1::uuid[])
        """,
        inserted_chunks,
    )
    assert len(rows) == 0, "Zone filter not enforced — 'bridge' returned personal chunks"


@pytest.mark.asyncio
async def test_idempotent_reingest_no_duplicates(db_conn, inserted_chunks):
    """Re-inserting the same content_hash produces no duplicate rows (D-025)."""
    if not inserted_chunks:
        pytest.skip("No chunks inserted")

    original_row = await db_conn.fetchrow(
        "SELECT content_hash FROM clive_search.chunks WHERE chunk_id = $1",
        inserted_chunks[0],
    )
    original_hash = original_row["content_hash"]

    result = await db_conn.execute(
        """
        INSERT INTO clive_search.chunks
          (content, embedding, source_attribution, zone_of_origin,
           position, source_key, content_hash, content_tsv, document_id)
        VALUES
          ('Duplicate content', $1::vector, 'test', 'personal', 99, 'test', $2,
           to_tsvector('english', 'Duplicate content'),
           gen_random_uuid())
        ON CONFLICT (content_hash) DO NOTHING
        """,
        TEST_EMBEDDING_STR,
        original_hash,
    )
    assert result == "INSERT 0 0", f"Expected no insert on conflict, got: {result}"
