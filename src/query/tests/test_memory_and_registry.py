"""Tests for query/memory.py and query/registry.py."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.registry import RegistryClient, ToolDescriptor


# ---------------------------------------------------------------------------
# memory.py — retrieve_entities
# ---------------------------------------------------------------------------

class TestRetrieveEntities:
    @pytest.mark.asyncio
    async def test_returns_entities_from_db(self):
        from query.memory import retrieve_entities

        eid = uuid.uuid4()
        mock_rows = [
            {
                "entity_id": eid,
                "entity_type": "person",
                "key": "colleague",
                "value": "Alice",
                "similarity_score": 0.95,
            }
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.memory.get_pool", return_value=mock_pool):
            result = await retrieve_entities([0.1] * 5, top_k=5)

        assert len(result) == 1
        assert result[0]["key"] == "colleague"
        assert result[0]["value"] == "Alice"
        assert result[0]["similarity_score"] == 0.95

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self):
        from query.memory import retrieve_entities

        with patch("query.memory.get_pool", side_effect=RuntimeError("pool down")):
            result = await retrieve_entities([0.1] * 5)

        assert result == []


# ---------------------------------------------------------------------------
# memory.py — store_entities
# ---------------------------------------------------------------------------

class TestStoreEntities:
    @pytest.mark.asyncio
    async def test_stores_entities_with_embeddings(self):
        from query.memory import store_entities

        entities = [
            {"entity_type": "fact", "key": "city", "value": "London"},
        ]
        embeddings = [[0.1] * 1536]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.memory.get_pool", return_value=mock_pool):
            await store_entities(entities, source_turn_id=None, embeddings=embeddings)

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_empty_entities(self):
        from query.memory import store_entities

        with patch("query.memory.get_pool") as mock_get_pool:
            await store_entities([], source_turn_id=None, embeddings=[])
            mock_get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_is_non_fatal(self):
        from query.memory import store_entities

        entities = [{"entity_type": "fact", "key": "city", "value": "London"}]
        embeddings = [[0.1] * 1536]

        with patch("query.memory.get_pool", side_effect=RuntimeError("pool down")):
            # Should not raise
            await store_entities(entities, source_turn_id=None, embeddings=embeddings)


# ---------------------------------------------------------------------------
# memory.py — consolidate_if_needed
# ---------------------------------------------------------------------------

class TestConsolidateIfNeeded:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_immediately(self):
        from query.memory import consolidate_if_needed

        old_time = datetime.now(timezone.utc) - timedelta(hours=1)  # Less than 48h
        meta_row = {"cnt": 5, "oldest": old_time}  # Less than 100 turns

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=meta_row)
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_summarise = AsyncMock()

        with patch("query.memory.get_pool", return_value=mock_pool):
            await consolidate_if_needed(uuid.uuid4(), mock_summarise)

        # LLM should not have been called
        mock_summarise.assert_not_called()

    @pytest.mark.asyncio
    async def test_triggers_on_high_turn_count(self):
        from query.memory import consolidate_if_needed

        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        meta_row = {"cnt": 150, "oldest": old_time}  # > 100 turns

        turn_rows = [
            {"turn_id": uuid.uuid4(), "turn_number": i, "role": "user", "content": f"msg {i}"}
            for i in range(50)
        ]

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=meta_row)
        mock_conn.fetch = AsyncMock(return_value=turn_rows)
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_summarise = AsyncMock(return_value=("Summary text.", [0.5] * 1536))

        with patch("query.memory.get_pool", return_value=mock_pool):
            await consolidate_if_needed(uuid.uuid4(), mock_summarise)

        mock_summarise.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_turns_returns_early(self):
        from query.memory import consolidate_if_needed

        meta_row = {"cnt": 0, "oldest": None}

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=meta_row)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_summarise = AsyncMock()

        with patch("query.memory.get_pool", return_value=mock_pool):
            await consolidate_if_needed(uuid.uuid4(), mock_summarise)

        mock_summarise.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_is_non_fatal(self):
        from query.memory import consolidate_if_needed

        with patch("query.memory.get_pool", side_effect=RuntimeError("pool down")):
            # Should not raise
            await consolidate_if_needed(uuid.uuid4(), AsyncMock())


# ---------------------------------------------------------------------------
# registry.py — RegistryClient
# ---------------------------------------------------------------------------

class TestRegistryClient:
    @pytest.mark.asyncio
    async def test_get_tools_triggers_refresh_on_first_call(self):
        client = RegistryClient()

        mock_rows = [
            {
                "tool_name": "web_search",
                "display_name": "Web Search",
                "description": "Search the web",
                "permission_scope": ["owner"],
            }
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.registry.get_pool", return_value=mock_pool):
            tools = await client.get_tools()

        assert len(tools) == 1
        assert tools[0].tool_name == "web_search"

    @pytest.mark.asyncio
    async def test_get_tools_uses_cache_within_ttl(self):
        client = RegistryClient()
        client._cache = [ToolDescriptor(tool_name="cached_tool", display_name="Cached", description="From cache")]
        client._cache_ts = time.monotonic()  # just refreshed

        with patch("query.registry.get_pool") as mock_pool:
            tools = await client.get_tools()
            mock_pool.assert_not_called()

        assert len(tools) == 1
        assert tools[0].tool_name == "cached_tool"

    @pytest.mark.asyncio
    async def test_refresh_retains_stale_cache_on_db_error(self):
        client = RegistryClient()
        stale_tool = ToolDescriptor(tool_name="stale_tool", display_name="Stale", description="Old")
        client._cache = [stale_tool]
        client._cache_ts = 0.0  # expired

        with patch("query.registry.get_pool", side_effect=RuntimeError("db down")):
            await client.refresh()

        # Cache should still contain the stale tool
        assert len(client._cache) == 1
        assert client._cache[0].tool_name == "stale_tool"

    @pytest.mark.asyncio
    async def test_get_tools_returns_snapshot_copy(self):
        """Callers cannot mutate the internal cache."""
        client = RegistryClient()
        client._cache = [ToolDescriptor(tool_name="t", display_name="T", description="d")]
        client._cache_ts = time.monotonic()

        tools = await client.get_tools()
        tools.clear()  # Mutate the returned copy

        # Internal cache should be unchanged
        assert len(client._cache) == 1

    @pytest.mark.asyncio
    async def test_empty_registry_returns_empty_list(self):
        client = RegistryClient()

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.registry.get_pool", return_value=mock_pool):
            tools = await client.get_tools()

        assert tools == []


# ---------------------------------------------------------------------------
# spend.py — record_usage and get_daily_cap_from_config
# ---------------------------------------------------------------------------

class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_inserts_usage_row(self):
        from query.spend import record_usage

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.spend.get_pool", return_value=mock_pool):
            await record_usage(
                model="anthropic/claude-sonnet-4-20250514",
                prompt_tokens=1000,
                completion_tokens=500,
                cost_usd=0.0105,
            )

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_error_is_non_fatal(self):
        from query.spend import record_usage

        with patch("query.spend.get_pool", side_effect=RuntimeError("pool down")):
            # Should not raise
            await record_usage("model", 10, 5, 0.001)


class TestGetDailyCapFromConfig:
    @pytest.mark.asyncio
    async def test_returns_float_from_config(self):
        from query.spend import get_daily_cap_from_config

        mock_row = {"config_value": "7.5"}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.spend.get_pool", return_value=mock_pool):
            result = await get_daily_cap_from_config()

        assert result == pytest.approx(7.5)

    @pytest.mark.asyncio
    async def test_returns_none_when_key_missing(self):
        from query.spend import get_daily_cap_from_config

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.spend.get_pool", return_value=mock_pool):
            result = await get_daily_cap_from_config()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self):
        from query.spend import get_daily_cap_from_config

        with patch("query.spend.get_pool", side_effect=RuntimeError("pool down")):
            result = await get_daily_cap_from_config()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_float_value(self):
        from query.spend import get_daily_cap_from_config

        mock_row = {"config_value": "not-a-float"}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.spend.get_pool", return_value=mock_pool):
            result = await get_daily_cap_from_config()

        assert result is None


# ---------------------------------------------------------------------------
# query/db.py
# ---------------------------------------------------------------------------

class TestQueryDb:
    def test_get_pool_raises_when_not_init(self):
        from query import db

        original = db._pool
        try:
            db._pool = None
            with pytest.raises(RuntimeError, match="DB pool not initialised"):
                db.get_pool()
        finally:
            db._pool = original

    def test_get_pool_returns_pool_when_set(self):
        from query import db

        original = db._pool
        try:
            mock_pool = MagicMock()
            db._pool = mock_pool
            result = db.get_pool()
            assert result is mock_pool
        finally:
            db._pool = original
