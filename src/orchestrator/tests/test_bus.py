"""Tests for in-process event bus."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.bus import EventBus
from orchestrator.events.schema import AlignmentResult, CLIVEEvent
from orchestrator.events.taxonomy import QUERY_RECEIVED, QUERY_RESPONSE


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_subscriber_receives_event(bus):
    received = []

    async def handler(event: CLIVEEvent) -> None:
        await asyncio.sleep(0)
        received.append(event)

    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=handler)

    with patch("orchestrator.bus.alignment.check", return_value=AlignmentResult.PASS), \
         patch("orchestrator.bus.audit.write", new_callable=AsyncMock):
        event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
        await bus.publish(event)
        # Allow queue processing
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].event_type == QUERY_RECEIVED


@pytest.mark.asyncio
async def test_alignment_failure_prevents_dispatch(bus):
    received = []

    async def handler(event: CLIVEEvent) -> None:
        await asyncio.sleep(0)
        received.append(event)

    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=handler)

    with patch("orchestrator.bus.alignment.check", return_value=AlignmentResult.FAIL), \
         patch("orchestrator.bus.audit.write", new_callable=AsyncMock):
        event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
        await bus.publish(event)
        await asyncio.sleep(0.05)

    assert len(received) == 0
