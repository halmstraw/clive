"""Tests for processing/store.py — PostgreSQL chunk writer."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWriteChunks:
    @pytest.mark.asyncio
    async def test_inserts_chunks_and_returns_count(self):
        from processing.store import write_chunks

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        chunks = ["chunk A", "chunk B"]
        embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        hashes = ["hash_a", "hash_b"]

        from processing import store
        original_pool = store._pool
        try:
            store._pool = mock_pool
            result = await write_chunks(chunks, embeddings, "raw/doc.pdf", hashes)
        finally:
            store._pool = original_pool

        assert result == 2
        assert mock_conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_duplicate_chunks(self):
        """ON CONFLICT DO NOTHING returns INSERT 0 0 for duplicates."""
        from processing import store

        mock_conn = AsyncMock()
        # First chunk inserts, second is a duplicate
        mock_conn.execute = AsyncMock(side_effect=["INSERT 0 1", "INSERT 0 0"])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = store._pool
        try:
            store._pool = mock_pool
            result = await store.write_chunks(
                ["chunk A", "chunk B"],
                [[0.1], [0.2]],
                "raw/doc.pdf",
                ["hash_a", "hash_a_dup"],
            )
        finally:
            store._pool = original_pool

        # Only 1 was actually inserted
        assert result == 1

    @pytest.mark.asyncio
    async def test_raises_when_pool_not_init(self):
        from processing import store

        original_pool = store._pool
        try:
            store._pool = None
            with pytest.raises(RuntimeError, match="Store pool not initialised"):
                await store.write_chunks(["chunk"], [[0.1]], "key", ["hash"])
        finally:
            store._pool = original_pool

    @pytest.mark.asyncio
    async def test_uses_zone_scope_in_insert(self):
        from processing import store

        executed_sqls = []

        mock_conn = AsyncMock()

        async def capture_execute(sql, *args):
            executed_sqls.append((sql, args))
            return "INSERT 0 1"

        mock_conn.execute = AsyncMock(side_effect=capture_execute)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = store._pool
        try:
            store._pool = mock_pool
            await store.write_chunks(
                ["chunk text"],
                [[0.1, 0.2]],
                "raw/test.pdf",
                ["hash_123"],
                zone_scope="work",
            )
        finally:
            store._pool = original_pool

        # Check the zone_scope was passed to the execute call
        assert len(executed_sqls) == 1
        _, args = executed_sqls[0]
        assert "work" in args  # zone_scope passed as parameter

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_zero(self):
        from processing import store

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = store._pool
        try:
            store._pool = mock_pool
            result = await store.write_chunks([], [], "raw/doc.pdf", [])
        finally:
            store._pool = original_pool

        assert result == 0
        mock_conn.execute.assert_not_called()
