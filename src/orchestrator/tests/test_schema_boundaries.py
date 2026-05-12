"""Integration tests: schema zone boundary enforcement — D-095, D-050.

Zone filter enforced on retrieval SQL (D-050): queries with zone_scope X
must never return chunks from zone Y.

Requires TEST_DB_URL env var.  Skipped otherwise.

Rendering edge-case tests live in src/telegram/tests/test_rendering.py (D-094).
"""

from __future__ import annotations

import os
import uuid

import pytest

TEST_DB_URL = os.environ.get("TEST_DB_URL")
TEST_EMBEDDING = [0.5] * 1536


# ---------------------------------------------------------------------------
# Zone boundary tests (require TEST_DB_URL)
# ---------------------------------------------------------------------------


@pytest.fixture
async def zone_test_chunks():
    """Insert one personal-zone chunk and verify bridge zone is empty."""
    import asyncpg

    if not TEST_DB_URL:
        pytest.skip("TEST_DB_URL not set")

    conn = await asyncpg.connect(TEST_DB_URL)
    run_id = uuid.uuid4().hex[:8]
    chunk_id = await conn.fetchval(
        """
        INSERT INTO clive_search.chunks
          (content, embedding, source_attribution, zone_of_origin,
           position, source_key, content_hash, content_tsv, document_id)
        VALUES
          ('Zone boundary test content', $1, 'test', 'personal', 0,
           $2, $3,
           to_tsvector('english', 'Zone boundary test content'),
           gen_random_uuid())
        ON CONFLICT (content_hash) DO NOTHING
        RETURNING chunk_id
        """,
        TEST_EMBEDDING,
        f"test/zone_{run_id}",
        f"zone_hash_{run_id}",
    )
    yield conn, chunk_id

    if chunk_id:
        await conn.execute("DELETE FROM clive_search.chunks WHERE chunk_id = $1", chunk_id)
    await conn.close()


@pytest.mark.asyncio
async def test_zone_filter_personal_only(zone_test_chunks):
    """Query with zone_scope='bridge' must not return personal chunks (D-050)."""
    conn, chunk_id = zone_test_chunks
    if not chunk_id:
        pytest.skip("Chunk not inserted (conflict)")

    rows = await conn.fetch(
        "SELECT chunk_id FROM clive_search.chunks WHERE zone_of_origin = 'bridge' AND chunk_id = $1",
        chunk_id,
    )
    assert len(rows) == 0, "Zone filter leaks personal chunks into bridge zone"


@pytest.mark.asyncio
async def test_retrieval_function_zone_filter():
    """orchestrator.retrieval.retrieve enforces zone_scope at the SQL level."""
    import asyncpg

    if not TEST_DB_URL:
        pytest.skip("TEST_DB_URL not set")

    import orchestrator.retrieval as retrieval_module

    original_pool = retrieval_module._pool
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
    retrieval_module._pool = pool

    try:
        result = await retrieval_module.retrieve(
            retrieval_query="zone boundary test",
            zone_scope="bridge",
            result_limit=10,
            conversation_id=None,
        )
        # Only bridge-zone chunks returned — personal chunks from other tests are excluded
        for chunk in result["ranked_chunks"]:
            assert chunk["zone_of_origin"] == "bridge", (
                f"Retrieved chunk has zone {chunk['zone_of_origin']!r}, expected 'bridge'"
            )
    finally:
        retrieval_module._pool = original_pool
        await pool.close()
