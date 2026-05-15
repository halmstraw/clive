"""Tests for retrieval broker (unit-level — no DB required)."""

from __future__ import annotations

import uuid

import pytest

import orchestrator.retrieval as retrieval_module


# ---------------------------------------------------------------------------
# Pool not initialised guards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve(
            retrieval_query="test",
            zone_scope="personal",
            result_limit=5,
            conversation_id=None,
        )


@pytest.mark.asyncio
async def test_retrieve_system_document_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_system_document(
            document_type="personality",
            zone_scope="personal",
        )


@pytest.mark.asyncio
async def test_retrieve_document_list_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_document_list(zone_scope="personal")


@pytest.mark.asyncio
async def test_retrieve_status_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_status(zone_scope="personal")


# ---------------------------------------------------------------------------
# Conversation memory — pool not initialised returns safe defaults
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_conversation_history_returns_empty_when_pool_not_initialised():
    """get_conversation_history must return [] (not raise) when pool is None.

    D-115: memory failures are non-fatal — query proceeds without history.
    """
    retrieval_module._pool = None
    result = await retrieval_module.get_conversation_history(uuid.uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_store_conversation_turn_noop_when_pool_not_initialised():
    """store_conversation_turn must not raise when pool is None.

    D-115: memory failures are non-fatal.
    """
    retrieval_module._pool = None
    # Should return None silently
    result = await retrieval_module.store_conversation_turn(
        event_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="user",
        content="test message",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Conversation history — ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_conversation_history_returns_chronological_order():
    """History must be returned oldest-first (reversed from DESC DB query)."""
    from unittest.mock import AsyncMock, MagicMock

    class FakeRow:
        def __init__(self, role, content):
            self._data = {"role": role, "content": content}
        def __getitem__(self, key):
            return self._data[key]

    # DB returns newest-first (DESC), history reverses to oldest-first
    db_rows = [
        FakeRow("assistant", "Second response"),
        FakeRow("user", "Second query"),
        FakeRow("assistant", "First response"),
        FakeRow("user", "First query"),
    ]

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=db_rows)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    retrieval_module._pool = pool

    result = await retrieval_module.get_conversation_history(uuid.uuid4(), limit=4)

    assert len(result) == 4
    # Chronological order (reversed from DESC DB output)
    assert result[0] == {"role": "user", "content": "First query"}
    assert result[1] == {"role": "assistant", "content": "First response"}
    assert result[2] == {"role": "user", "content": "Second query"}
    assert result[3] == {"role": "assistant", "content": "Second response"}

    retrieval_module._pool = None
