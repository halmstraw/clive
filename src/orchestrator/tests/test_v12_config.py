"""Tests for v0.12 self-knowledge retrieval + config handler (D-149, D-150)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import orchestrator.retrieval as retrieval_module


# ── Pool-not-initialised guards ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_action_history_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_action_history(zone_scope="personal")


@pytest.mark.asyncio
async def test_retrieve_workers_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_workers()


# ── retrieve_action_history ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_action_history_unknown_zone_returns_empty():
    """Unknown zone returns empty result immediately (D-143 pattern)."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.fetchrow = AsyncMock(return_value=None)  # zone not found

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    retrieval_module._pool = mock_pool

    result = await retrieval_module.retrieve_action_history(zone_scope="unknown_zone")
    assert result["actions"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_retrieve_action_history_returns_actions_from_db():
    """Returns resolved actions with correct field mapping."""
    from datetime import datetime, timezone

    fake_rows = [
        {
            "action_request_id": uuid.uuid4(),
            "action_type": "web.search",
            "action_target": "AI news",
            "action_description": "Search the web for: AI news",
            "status": "confirmed",
            "created_at": datetime(2026, 5, 17, 10, 0, 0, tzinfo=timezone.utc),
            "zone_scope": "personal",
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    # zone check returns a row (zone is valid)
    mock_conn.fetchrow = AsyncMock(return_value={"zone_name": "personal"})
    mock_conn.fetch = AsyncMock(return_value=fake_rows)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    retrieval_module._pool = mock_pool

    result = await retrieval_module.retrieve_action_history(zone_scope="personal", days=7)
    assert result["total"] == 1
    assert result["days"] == 7
    action = result["actions"][0]
    assert action["action_type"] == "web.search"
    assert action["action_target"] == "AI news"
    assert action["status"] == "confirmed"


# ── retrieve_workers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_workers_returns_workers_from_db():
    """Returns worker rows joined from workers + tool_registry tables."""
    from datetime import datetime, timezone

    now = datetime(2026, 5, 17, 8, 0, 0, tzinfo=timezone.utc)
    fake_rows = [
        {
            "worker_name": "daily_digest",
            "display_name": "Daily Digest",
            "description": "Delivers daily summary",
            "enabled": True,
            "health_status": "healthy",
            "schedule_type": "cron",
            "cron_expression": "0 8 * * *",
            "last_run_at": now,
            "next_run_at": None,
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.fetch = AsyncMock(return_value=fake_rows)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    retrieval_module._pool = mock_pool

    result = await retrieval_module.retrieve_workers()
    assert result["total"] == 1
    w = result["workers"][0]
    assert w["tool_name"] == "daily_digest"
    assert w["schedule"] == "0 8 * * *"
    assert w["enabled"] is True
    assert "2026-05-17" in w["last_run_at"]
    assert w["next_run_at"] is None
