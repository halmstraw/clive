"""Tests for Block 9 — Action Layer.

D-006: confirmation gate — no irreversible action without explicit confirmation.
D-025: idempotent — duplicate action_request_id handled gracefully.
Timeout equals rejection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.action import (
    _build_rejection_event,
    handle_action_owner_response,
    handle_action_pending,
)
from orchestrator.events.schema import CLIVEEvent
from orchestrator.events.taxonomy import (
    ACTION_CONFIRMATION_REQUESTED,
    ACTION_CONFIRMED,
    ACTION_OWNER_RESPONSE,
    ACTION_PENDING,
    ACTION_REJECTED,
)


def _make_pending_event(
    action_request_id: uuid.UUID | None = None,
    action_type: str = "document.delete",
    action_target: str = "report.pdf",
    chat_id: int = 12345,
) -> CLIVEEvent:
    payload: dict = {
        "action_type": action_type,
        "action_target": action_target,
        "action_description": f"Delete {action_target}.",
        "chat_id": chat_id,
    }
    if action_request_id:
        payload["action_request_id"] = str(action_request_id)
    return CLIVEEvent(
        event_type=ACTION_PENDING,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload=payload,
    )


def _make_response_event(
    action_request_id: uuid.UUID,
    confirmed: bool,
    chat_id: int = 12345,
) -> CLIVEEvent:
    return CLIVEEvent(
        event_type=ACTION_OWNER_RESPONSE,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload={
            "action_request_id": str(action_request_id),
            "confirmed": confirmed,
            "chat_id": chat_id,
        },
    )


@pytest.fixture
def mock_pool_factory():
    """Return a factory that creates a mock asyncpg pool with configurable fetchrow."""

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


@pytest.mark.asyncio
async def test_handle_action_pending_stores_and_emits_confirmation(mock_pool_factory):
    """action.pending must store the action and emit action.confirmation_requested."""
    pool, conn = mock_pool_factory(fetchrow_return=None)  # No existing record
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    # action.py does `from .bus import bus as _bus` inside the function.
    # Patch the module-level singleton so the lazy import picks up the mock.
    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_pending_event()
        await handle_action_pending(event)

    # Exactly one event emitted: action.confirmation_requested
    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_CONFIRMATION_REQUESTED
    assert emitted_events[0].source_block == 9
    assert "action_request_id" in emitted_events[0].payload
    assert emitted_events[0].payload["action_type"] == "document.delete"
    assert emitted_events[0].payload["action_target"] == "report.pdf"


@pytest.mark.asyncio
async def test_handle_action_pending_idempotent_on_duplicate(mock_pool_factory):
    """D-025: duplicate action_request_id re-emits confirmation_requested."""
    action_request_id = uuid.uuid4()
    # Existing row with status=pending → should re-emit
    pool, conn = mock_pool_factory(fetchrow_return={"status": "pending"})
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_pending_event(action_request_id=action_request_id)
        await handle_action_pending(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_CONFIRMATION_REQUESTED


@pytest.mark.asyncio
async def test_handle_action_pending_already_resolved_no_emit(mock_pool_factory):
    """D-025: already-confirmed action must not re-emit confirmation."""
    action_request_id = uuid.uuid4()
    pool, conn = mock_pool_factory(fetchrow_return={"status": "confirmed"})
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_pending_event(action_request_id=action_request_id)
        await handle_action_pending(event)

    assert len(emitted_events) == 0


@pytest.mark.asyncio
async def test_owner_confirmed_emits_action_confirmed(mock_pool_factory):
    """Owner confirmation must emit action.confirmed with action details."""
    action_request_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=120)

    db_row = {
        "action_type": "document.delete",
        "action_target": "report.pdf",
        "action_description": "Delete report.pdf.",
        "conversation_id": uuid.uuid4(),
        "chat_id": 12345,
        "status": "pending",
        "expires_at": expires_at,
    }
    pool, conn = mock_pool_factory(fetchrow_return=db_row)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_response_event(action_request_id, confirmed=True)
        await handle_action_owner_response(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_CONFIRMED
    assert emitted_events[0].payload["action_type"] == "document.delete"
    assert emitted_events[0].payload["action_target"] == "report.pdf"


@pytest.mark.asyncio
async def test_owner_rejected_emits_action_rejected(mock_pool_factory):
    """Owner rejection must emit action.rejected."""
    action_request_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    db_row = {
        "action_type": "document.delete",
        "action_target": "report.pdf",
        "action_description": "Delete report.pdf.",
        "conversation_id": uuid.uuid4(),
        "chat_id": 12345,
        "status": "pending",
        "expires_at": now + timedelta(seconds=120),
    }
    pool, conn = mock_pool_factory(fetchrow_return=db_row)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_response_event(action_request_id, confirmed=False)
        await handle_action_owner_response(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_REJECTED
    assert emitted_events[0].payload["reason"] == "owner_rejected"


@pytest.mark.asyncio
async def test_expired_action_emits_rejection(mock_pool_factory):
    """D-006: timeout equals rejection — expired action must emit action.rejected."""
    action_request_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    # expires_at is in the past
    expired_at = now - timedelta(seconds=1)

    db_row = {
        "action_type": "document.delete",
        "action_target": "report.pdf",
        "action_description": "Delete report.pdf.",
        "conversation_id": uuid.uuid4(),
        "chat_id": 12345,
        "status": "pending",
        "expires_at": expired_at,
    }
    pool, conn = mock_pool_factory(fetchrow_return=db_row)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_response_event(action_request_id, confirmed=True)
        await handle_action_owner_response(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_REJECTED
    assert emitted_events[0].payload["reason"] == "timed_out"


@pytest.mark.asyncio
async def test_response_for_not_found_action_emits_rejection(mock_pool_factory):
    """Response for unknown action_request_id must emit rejection, not crash."""
    action_request_id = uuid.uuid4()
    pool, conn = mock_pool_factory(fetchrow_return=None)  # Not found in DB
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    emitted_events = []

    import orchestrator.bus as bus_module
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock(side_effect=lambda e: emitted_events.append(e))

    with patch("orchestrator.action._pool", pool), \
         patch("orchestrator.audit.write", new_callable=AsyncMock), \
         patch.object(bus_module, "bus", mock_bus):
        event = _make_response_event(action_request_id, confirmed=True)
        await handle_action_owner_response(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].event_type == ACTION_REJECTED
    assert emitted_events[0].payload["reason"] == "not_found"


def test_build_rejection_event_has_correct_fields():
    """_build_rejection_event must include all required audit fields."""
    action_request_id = uuid.uuid4()
    event = _build_rejection_event(
        action_request_id=action_request_id,
        action_type="document.delete",
        action_target="report.pdf",
        reason="owner_rejected",
        conversation_id=uuid.uuid4(),
        chat_id=12345,
    )
    assert event.event_type == ACTION_REJECTED
    assert event.source_block == 9
    assert event.payload["action_request_id"] == str(action_request_id)
    assert event.payload["reason"] == "owner_rejected"
    assert event.payload["chat_id"] == 12345
