"""Tests for v0.9 chunk retrieval tracking — Block 16 (D-140, D-141).

After each fresh query that returns non-empty chunk_ids, Block 8 increments
retrieval_count and updates last_retrieved_at on the returned chunks.
This enables the knowledge_maintenance worker (Wave 3-B) to identify stale,
unaccessed chunks for owner review.

Acceptance criteria verified here:
  - After a fresh query with non-empty chunk_ids: pool.execute is called with
    the correct SQL and the correct chunk_ids (the core AC).
  - When chunk_ids is empty: pool.execute is NOT called (no spurious write).
  - On DB failure: exception is caught, WARN logged, no re-raise (non-fatal).
  - On cache hits (D-046): tracking is not called (only fresh retrievals tracked).

All tests mock the DB pool. No live DB calls in CI (D-095).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from query.handler import _update_chunk_retrieval_stats


# ── Direct unit tests for _update_chunk_retrieval_stats ──────────────────────

@pytest.mark.asyncio
async def test_retrieval_tracking_calls_execute_with_correct_chunk_ids():
    """Core AC: non-empty chunk_ids → pool.execute called with correct chunk_ids."""
    chunk_ids = [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]

    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock(return_value=None)

    with patch("query.handler.get_pool", return_value=mock_pool):
        await _update_chunk_retrieval_stats(chunk_ids)

    mock_pool.execute.assert_called_once()
    call_args = mock_pool.execute.call_args
    # First positional arg is the SQL query; second is chunk_ids
    sql_executed = call_args[0][0]
    ids_passed = call_args[0][1]

    assert "retrieval_count = retrieval_count + 1" in sql_executed
    assert "last_retrieved_at = NOW()" in sql_executed
    assert "$1::uuid[]" in sql_executed
    assert ids_passed == chunk_ids


@pytest.mark.asyncio
async def test_retrieval_tracking_skipped_when_chunk_ids_empty():
    """Empty chunk_ids → pool.execute NOT called (no spurious DB write)."""
    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock(return_value=None)

    with patch("query.handler.get_pool", return_value=mock_pool):
        await _update_chunk_retrieval_stats([])

    mock_pool.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retrieval_tracking_does_not_raise_on_db_failure():
    """DB pool raises → exception caught, WARN logged, no re-raise (non-fatal)."""
    chunk_ids = [str(uuid.uuid4())]

    with patch(
        "query.handler.get_pool",
        side_effect=RuntimeError("pool not initialised"),
    ):
        # Must not raise — non-fatal by design
        await _update_chunk_retrieval_stats(chunk_ids)


@pytest.mark.asyncio
async def test_retrieval_tracking_does_not_raise_on_execute_failure():
    """pool.execute raises → exception caught, no re-raise (non-fatal)."""
    chunk_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock(side_effect=Exception("connection error"))

    with patch("query.handler.get_pool", return_value=mock_pool):
        # Must not raise
        await _update_chunk_retrieval_stats(chunk_ids)

    mock_pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_retrieval_tracking_called_with_all_chunk_ids_not_subset():
    """All chunk_ids from retrieval are passed — not a subset or truncated list."""
    chunk_ids = [str(uuid.uuid4()) for _ in range(20)]  # max retrieval batch

    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock(return_value=None)

    with patch("query.handler.get_pool", return_value=mock_pool):
        await _update_chunk_retrieval_stats(chunk_ids)

    call_args = mock_pool.execute.call_args
    ids_passed = call_args[0][1]
    assert len(ids_passed) == 20
    assert ids_passed == chunk_ids


# ── Cache-hit integration: tracking must NOT fire on cache hits (D-046) ───────

@pytest.mark.asyncio
async def test_retrieval_tracking_not_called_on_cache_hit():
    """On a cache hit (D-046), _update_chunk_retrieval_stats must not be called.

    The idempotency check at step 1 returns early before any retrieval occurs.
    Therefore chunk_ids never exists on the cache-hit path, and the tracking
    function is never reached.
    """
    event_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())

    event = {
        "event_id": event_id,
        "conversation_id": conversation_id,
        "input_text": "what is the speed of light?",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    cached_payload = {
        "event_id": event_id,
        "response_text": "Approximately 299,792,458 metres per second.",
        "confidence": {"chunks_returned": 3, "highest_relevance_score": 0.9, "threshold_met": True},
        "chunk_ids": [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())],
    }

    tracking_calls: list = []

    async def fake_tracking(chunk_ids: list) -> None:  # NOSONAR
        tracking_calls.append(chunk_ids)

    async def fake_emit(event_type: str, payload: dict) -> None:  # NOSONAR
        pass

    with (
        patch("query.handler.cache.get", return_value=cached_payload),
        patch("query.handler._emit_event", side_effect=fake_emit),
        patch("query.handler._update_chunk_retrieval_stats", side_effect=fake_tracking),
    ):
        from query.handler import handle_query
        await handle_query(event)

    # On a cache hit, handle_query returns early — tracking must not be called
    assert len(tracking_calls) == 0, (
        "Retrieval tracking must not be called on cache hits (D-046)"
    )
