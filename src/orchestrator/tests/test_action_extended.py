"""Extended tests for action.py — covering remaining uncovered paths."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import AlignmentResult, CLIVEEvent
from orchestrator.events.taxonomy import ACTION_OWNER_RESPONSE


def _make_response_event(action_request_id: str | None = None, confirmed: bool = True) -> CLIVEEvent:
    payload: dict = {"confirmed": confirmed, "chat_id": 12345}
    if action_request_id is not None:
        payload["action_request_id"] = action_request_id
    return CLIVEEvent(
        event_type=ACTION_OWNER_RESPONSE,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload=payload,
    )


@pytest.fixture
def mock_pool_factory():
    def _make(fetchrow_return=None, fetch_return=None):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=fetchrow_return)
        conn.fetch = AsyncMock(return_value=fetch_return or [])
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)
        pool = AsyncMock()
        pool.acquire = MagicMock(return_value=conn)
        return pool, conn
    return _make


# ---------------------------------------------------------------------------
# handle_action_owner_response — missing action_request_id (lines 188-189)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_response_missing_action_request_id_returns_early(mock_pool_factory):
    """When action_request_id is absent from payload, function returns immediately."""
    from orchestrator.action import handle_action_owner_response

    event = _make_response_event(action_request_id=None)
    pool, _ = mock_pool_factory()

    with patch("orchestrator.action._pool", pool):
        await handle_action_owner_response(event)

    # Pool should not have been touched
    pool.acquire.assert_not_called()


# ---------------------------------------------------------------------------
# handle_action_owner_response — already resolved (lines 228-233)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_response_already_resolved_returns_early(mock_pool_factory):
    """When status is 'confirmed', function returns without re-publishing."""
    from orchestrator.action import handle_action_owner_response

    rid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    pool, conn = mock_pool_factory(fetchrow_return={
        "action_type": "document.delete",
        "action_target": "report.pdf",
        "action_description": "Delete report.pdf",
        "conversation_id": uuid.uuid4(),
        "chat_id": 12345,
        "status": "confirmed",  # already resolved
        "expires_at": now + timedelta(seconds=120),
        "metadata": "{}",
    })

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    with (
        patch("orchestrator.action._pool", pool),
        patch("orchestrator.audit.write", AsyncMock()),
        patch.object(bus_module, "bus", mock_bus),
    ):
        event = _make_response_event(action_request_id=str(rid))
        await handle_action_owner_response(event)

    # No publish should happen since it's already resolved
    mock_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# _get_pool — raises when not initialised (line 71)
# ---------------------------------------------------------------------------

def test_action_get_pool_raises_when_not_init():
    from orchestrator.action import _get_pool
    import orchestrator.action as action_mod

    original = action_mod._pool
    try:
        action_mod._pool = None
        with pytest.raises(RuntimeError, match="Action pool not initialised"):
            _get_pool()
    finally:
        action_mod._pool = original


# ---------------------------------------------------------------------------
# timeout_checker — test one iteration (lines 339-373)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_checker_rejects_expired_action(mock_pool_factory):
    """timeout_checker runs, finds expired actions, rejects them."""
    from orchestrator.action import timeout_checker

    rid = uuid.uuid4()
    cid = uuid.uuid4()
    expired_row = {
        "action_request_id": rid,
        "action_type": "document.delete",
        "action_target": "old.pdf",
        "conversation_id": cid,
        "chat_id": 12345,
    }

    pool, conn = mock_pool_factory(fetch_return=[expired_row])
    conn.execute = AsyncMock()

    published_events = []
    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: published_events.append(e))

    with (
        patch("orchestrator.action._pool", pool),
        patch("orchestrator.audit.write", AsyncMock()),
        patch.object(bus_module, "bus", mock_bus),
        # Only let the loop run once, then cancel
        patch("orchestrator.action.asyncio.sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])),
    ):
        with pytest.raises(asyncio.CancelledError):
            await timeout_checker(mock_bus)

    # Should have published a rejection event for the expired action
    assert any("timed_out" in str(e.payload) for e in published_events)


@pytest.mark.asyncio
async def test_timeout_checker_handles_db_error_gracefully(mock_pool_factory):
    """timeout_checker catches exceptions and keeps running."""
    from orchestrator.action import timeout_checker

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    with (
        patch("orchestrator.action._pool", MagicMock(acquire=MagicMock(side_effect=Exception("db error")))),
        patch("orchestrator.audit.write", AsyncMock()),
        patch.object(bus_module, "bus", mock_bus),
        patch("orchestrator.action.asyncio.sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])),
    ):
        with pytest.raises(asyncio.CancelledError):
            await timeout_checker(mock_bus)

    # Should not have published any events since DB errored
    mock_bus.publish.assert_not_called()
