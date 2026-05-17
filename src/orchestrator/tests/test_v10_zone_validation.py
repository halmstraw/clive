"""v0.10 — Block 8 zone validation and Block 9 zone propagation tests.

D-143: zone_scope validated against clive_state.zones before retrieval runs.
D-050: 'personal' is always a valid zone (seeded in Wave 1).
Fail-open: zone validation returns True when DB is unavailable (pool None or
DB error) so retrieval is never blocked by zone-check infrastructure failure.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import orchestrator.retrieval as retrieval_module
from orchestrator.events.schema import CLIVEEvent
from orchestrator.events.taxonomy import ACTION_PENDING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_retrieval_pool(fetchrow_return=None, fetch_return=None):
    """Build a mock asyncpg pool for retrieval tests.

    pool.acquire() returns a context manager that yields conn.
    conn.fetchrow() is used by _is_valid_zone; conn.fetch() is used by
    the retrieval queries themselves.
    """
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _make_action_pool(fetchrow_return=None):
    """Build a mock asyncpg pool for action tests (asyncpg pattern)."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock(return_value=None)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


# ---------------------------------------------------------------------------
# _is_valid_zone — fail-open when pool is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_valid_zone_returns_true_when_pool_none():
    """Fail open: returns True when pool is not initialised (D-143).

    Pool may not be ready during startup. Zone validation must not block
    retrieval in that transient window.
    """
    retrieval_module._pool = None
    try:
        result = await retrieval_module._is_valid_zone("personal")
        assert result is True
    finally:
        retrieval_module._pool = None


# ---------------------------------------------------------------------------
# _is_valid_zone — DB-backed results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_valid_zone_returns_true_for_known_zone():
    """Known zone ('personal') returns True when DB returns a matching row.

    D-050: 'personal' is seeded in Wave 1 and is always a valid zone.
    """
    pool, conn = _make_retrieval_pool(fetchrow_return={"1": 1})
    retrieval_module._pool = pool
    try:
        result = await retrieval_module._is_valid_zone("personal")
        assert result is True
        # Verify the query targeted the zones table with the correct parameter
        conn.fetchrow.assert_called_once()
        sql, zone_arg = conn.fetchrow.call_args.args
        assert "clive_state.zones" in sql
        assert zone_arg == "personal"
    finally:
        retrieval_module._pool = None


@pytest.mark.asyncio
async def test_is_valid_zone_returns_false_for_unknown_zone():
    """Unknown zone returns False when DB returns no matching row (D-143)."""
    pool, conn = _make_retrieval_pool(fetchrow_return=None)
    retrieval_module._pool = pool
    try:
        result = await retrieval_module._is_valid_zone("nonexistent_zone")
        assert result is False
    finally:
        retrieval_module._pool = None


@pytest.mark.asyncio
async def test_is_valid_zone_returns_true_on_db_error():
    """Fail open: returns True on DB error so retrieval is not blocked (D-143)."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=Exception("DB connection error"))
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    retrieval_module._pool = pool
    try:
        result = await retrieval_module._is_valid_zone("personal")
        assert result is True
    finally:
        retrieval_module._pool = None


# ---------------------------------------------------------------------------
# retrieve() — zone validation integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_unknown_zone():
    """retrieve() short-circuits with empty result for unknown zone (D-143).

    No SQL must be run against clive_search.chunks when zone is invalid.
    """
    # fetchrow returns None → zone is unknown
    pool, conn = _make_retrieval_pool(fetchrow_return=None)
    retrieval_module._pool = pool
    try:
        result = await retrieval_module.retrieve(
            retrieval_query="test query",
            zone_scope="nonexistent_zone",
            result_limit=5,
            conversation_id=None,
        )
        assert result == {"ranked_chunks": [], "result_count": 0}
        # conn.fetch must NOT be called — we returned before the retrieval query
        conn.fetch.assert_not_called()
    finally:
        retrieval_module._pool = None


@pytest.mark.asyncio
async def test_retrieve_proceeds_normally_for_known_zone():
    """retrieve() proceeds to the DB query when zone_scope='personal' (D-050).

    fetchrow (zone check) returns a row → zone is valid.
    fetch (retrieval query) returns one chunk → result is non-empty.
    """
    chunk_id = uuid.uuid4()

    class FakeChunkRow:
        """asyncpg row-like object for retrieval result."""
        _data = {
            "chunk_id": chunk_id,
            "content": "Test chunk content.",
            "source_attribution": "test_doc.pdf",
            "zone_of_origin": "personal",
            "text_score": 0.6,
            "vector_score": 0.4,
        }
        def __getitem__(self, key):
            return self._data[key]

    # fetchrow → non-None (zone valid); fetch → one chunk row
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"1": 1})
    conn.fetch = AsyncMock(return_value=[FakeChunkRow()])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    retrieval_module._pool = pool

    try:
        result = await retrieval_module.retrieve(
            retrieval_query="test query",
            zone_scope="personal",
            result_limit=5,
            conversation_id=uuid.uuid4(),
        )
        assert result["result_count"] == 1
        assert len(result["ranked_chunks"]) == 1
        chunk = result["ranked_chunks"][0]
        assert chunk["content"] == "Test chunk content."
        assert chunk["zone_of_origin"] == "personal"
        assert chunk["relevance_score"] == pytest.approx(1.0)
        # Both zone check and retrieval query were executed
        conn.fetchrow.assert_called_once()
        conn.fetch.assert_called_once()
    finally:
        retrieval_module._pool = None


# ---------------------------------------------------------------------------
# Block 9 — zone_scope propagated into pending_actions INSERT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_pending_insert_includes_zone_scope():
    """pending_actions INSERT carries zone_scope from event payload (D-143).

    The INSERT SQL must name the zone_scope column and the extracted value
    from the event payload must be passed as a positional parameter.
    """
    event = CLIVEEvent(
        event_type=ACTION_PENDING,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload={
            "action_type": "document.delete",
            "action_target": "test_document.pdf",
            "action_description": "Delete test_document.pdf",
            "chat_id": 99999,
            "zone_scope": "personal",
        },
    )

    pool, conn = _make_action_pool(fetchrow_return=None)  # no existing record

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    import orchestrator.action as action_module

    with (
        patch("orchestrator.action._pool", pool),
        patch("orchestrator.audit.write", new_callable=AsyncMock),
        patch.object(bus_module, "bus", mock_bus),
    ):
        await action_module.handle_action_pending(event)

    # conn.execute must have been called for the INSERT
    assert conn.execute.called, "conn.execute was not called — INSERT did not run"

    call_args = conn.execute.call_args
    sql: str = call_args.args[0]
    params: tuple = call_args.args[1:]

    # SQL must name the zone_scope column
    assert "zone_scope" in sql, f"Expected 'zone_scope' in INSERT SQL; got:\n{sql}"

    # 'personal' must appear in the positional parameters
    assert "personal" in params, (
        f"Expected 'personal' in INSERT params; got: {params}"
    )


@pytest.mark.asyncio
async def test_action_pending_defaults_zone_scope_to_personal():
    """zone_scope defaults to 'personal' when omitted from event payload (D-050)."""
    event = CLIVEEvent(
        event_type=ACTION_PENDING,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload={
            "action_type": "document.delete",
            "action_target": "another.pdf",
            "action_description": "Delete another.pdf",
            "chat_id": 12345,
            # zone_scope intentionally absent
        },
    )

    pool, conn = _make_action_pool(fetchrow_return=None)

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    import orchestrator.action as action_module

    with (
        patch("orchestrator.action._pool", pool),
        patch("orchestrator.audit.write", new_callable=AsyncMock),
        patch.object(bus_module, "bus", mock_bus),
    ):
        await action_module.handle_action_pending(event)

    assert conn.execute.called
    params: tuple = conn.execute.call_args.args[1:]
    assert "personal" in params, (
        f"Expected default 'personal' in INSERT params; got: {params}"
    )
