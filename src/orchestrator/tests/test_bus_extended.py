"""Extended tests for bus.py — covering remaining uncovered paths."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.bus import EventBus
from orchestrator.events.schema import AlignmentResult, CLIVEEvent
from orchestrator.events.taxonomy import QUERY_RECEIVED


# ---------------------------------------------------------------------------
# Override active — event held (lines 64-66)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_holds_event_when_override_active():
    """Events are held when system override is active."""
    bus = EventBus()
    bus.set_override(True)

    published = []
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=AsyncMock(side_effect=lambda e: published.append(e)))

    with (
        patch("orchestrator.bus.alignment.check", return_value=AlignmentResult.PASS),
        patch("orchestrator.bus.audit.write", AsyncMock()),
    ):
        event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
        await bus.publish(event)
        await asyncio.sleep(0.02)

    # Event should be held, not dispatched
    assert len(published) == 0


# ---------------------------------------------------------------------------
# set_override (lines 189-190)
# ---------------------------------------------------------------------------

def test_set_override_toggles_flag():
    bus = EventBus()
    assert bus._override_active is False

    bus.set_override(True)
    assert bus._override_active is True

    bus.set_override(False)
    assert bus._override_active is False


# ---------------------------------------------------------------------------
# Queue full backpressure (lines 97-103)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_full_drops_event():
    """When queue is at MAX_QUEUE_SIZE, new events are dropped (D-028)."""
    from orchestrator.bus import MAX_QUEUE_SIZE

    bus = EventBus()

    # Fill up the queue with events
    queue_key = "_system"
    bus._queues[queue_key] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    # Fill to capacity without a worker draining it
    for _ in range(MAX_QUEUE_SIZE):
        await bus._queues[queue_key].put(None)

    # Queue is now full — enqueue should drop the event
    event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
    await bus._enqueue(queue_key, event)

    # Still at MAX_QUEUE_SIZE (not MAX_QUEUE_SIZE + 1)
    assert bus._queues[queue_key].qsize() == MAX_QUEUE_SIZE


# ---------------------------------------------------------------------------
# _emit_delivery_failed (lines 169-180)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_delivery_failed_writes_audit():
    """_emit_delivery_failed writes a DELIVERY_FAILED event to audit."""
    bus = EventBus()
    event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)

    with patch("orchestrator.bus.audit.write", AsyncMock()) as mock_audit:
        await bus._emit_delivery_failed(event, block_id=8)

    mock_audit.assert_called_once()
    written_event = mock_audit.call_args[0][0]
    assert written_event.event_type == "delivery.failed"
    assert written_event.payload["subscriber_block"] == 8


# ---------------------------------------------------------------------------
# Dead-letter via exhausted retries (line 145)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_emits_delivery_failed_on_retry_exhaustion():
    """When all retries fail, _emit_delivery_failed is called."""
    from orchestrator.bus import RETRY_FAILED

    bus = EventBus()

    # Register a subscriber that always fails
    failing_handler = AsyncMock(side_effect=Exception("always fails"))
    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=failing_handler)

    event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)

    delivery_failed_calls = []

    async def capture_delivery_failed(e, block_id):
        delivery_failed_calls.append((e, block_id))

    with (
        patch("orchestrator.bus.with_retry", AsyncMock(return_value=RETRY_FAILED)),
        patch.object(bus, "_emit_delivery_failed", capture_delivery_failed),
    ):
        await bus._dispatch(event)

    assert len(delivery_failed_calls) == 1
    assert delivery_failed_calls[0][1] == 8
