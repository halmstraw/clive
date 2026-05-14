"""Tests for retry logic."""

from __future__ import annotations

import pytest

from orchestrator.retry import DELIVERY_FAILED, MAX_RETRIES, with_retry


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    calls = []

    async def fn():
        calls.append(1)
        return "ok"

    result = await with_retry(fn, event_id="test", subscriber_block=8)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_void_success_returns_none_not_sentinel():
    """Void push functions return None on success.
    with_retry must return None (not DELIVERY_FAILED) for void functions.
    The bus checks `is DELIVERY_FAILED` so void success is not mis-flagged.
    """
    async def void_fn():
        return None  # Simulates a void push function

    result = await with_retry(void_fn, event_id="test", subscriber_block=8)
    assert result is None
    assert result is not DELIVERY_FAILED


@pytest.mark.asyncio
async def test_returns_sentinel_after_exhaustion(monkeypatch):
    import orchestrator.retry as retry_module
    monkeypatch.setattr(retry_module, "INITIAL_BACKOFF", 0.001)

    calls = []

    async def fn():
        calls.append(1)
        raise RuntimeError("always fails")

    result = await with_retry(fn, event_id="test", subscriber_block=8)
    assert result is DELIVERY_FAILED
    assert len(calls) == MAX_RETRIES + 1


@pytest.mark.asyncio
async def test_succeeds_on_retry(monkeypatch):
    import orchestrator.retry as retry_module
    monkeypatch.setattr(retry_module, "INITIAL_BACKOFF", 0.001)

    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await with_retry(fn, event_id="test", subscriber_block=8)
    assert result == "ok"
    assert len(calls) == 3
