"""Tests for Block 20 — rate limiting and /status spend display.

D-126 criteria 3 and 6.
All tests mock external calls (orchestrator HTTP, Telegram bot).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Rate limiting — D-126 criterion 3
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    """Reset _rate_limit_state between tests."""
    import clive_telegram.bot as bot_module
    bot_module._rate_limit_state["hour"] = None
    bot_module._rate_limit_state["count"] = 0
    yield
    bot_module._rate_limit_state["hour"] = None
    bot_module._rate_limit_state["count"] = 0


def _make_update(text: str = "hello", chat_id: int = 12345) -> MagicMock:
    """Build a minimal mock Telegram Update."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.date = MagicMock()
    update.message.date.isoformat = MagicMock(return_value="2026-05-15T10:00:00")
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


@pytest.mark.asyncio
async def test_rate_limit_blocks_query_when_limit_reached():
    """When count >= RATE_LIMIT_QUERIES_PER_HOUR, query is rejected and not forwarded.
    D-126 criterion 3."""
    from clive_telegram.bot import handle_message, _rate_limit_state
    from datetime import datetime, timezone

    update = _make_update("tell me something")
    context = MagicMock()

    # Pre-fill the rate limit state to be at the limit
    current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _rate_limit_state["hour"] = current_hour
    _rate_limit_state["count"] = 5  # at the limit of 5

    mock_emit = AsyncMock()

    with (
        patch.dict(os.environ, {"RATE_LIMIT_QUERIES_PER_HOUR": "5"}),
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot._emit_to_orchestrator", mock_emit),
    ):
        await handle_message(update, context)

    # Query must NOT have been forwarded to orchestrator
    mock_emit.assert_not_called()

    # Rejection message must have been sent
    update.message.reply_text.assert_called_once()
    rejection_text = update.message.reply_text.call_args.args[0]
    assert "rate limit" in rejection_text.lower() or "limit" in rejection_text.lower()


@pytest.mark.asyncio
async def test_rate_limit_allows_query_under_limit():
    """When count < RATE_LIMIT_QUERIES_PER_HOUR, query is forwarded normally.
    D-126 criterion 3."""
    from clive_telegram.bot import handle_message, _rate_limit_state
    from datetime import datetime, timezone

    update = _make_update("what is the capital of France?")
    context = MagicMock()

    current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _rate_limit_state["hour"] = current_hour
    _rate_limit_state["count"] = 2  # under limit of 5

    mock_emit = AsyncMock()

    with (
        patch.dict(os.environ, {"RATE_LIMIT_QUERIES_PER_HOUR": "5"}),
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot._emit_to_orchestrator", mock_emit),
        patch("clive_telegram.bot.sessions") as mock_sessions,
    ):
        mock_sessions.get_or_create = MagicMock(return_value=__import__("uuid").uuid4())
        await handle_message(update, context)

    # query.received must have been emitted
    mock_emit.assert_called_once()
    assert mock_emit.call_args.args[0] == "query.received"


@pytest.mark.asyncio
async def test_rate_limit_resets_on_new_hour():
    """Counter resets at the top of a new UTC clock hour."""
    from clive_telegram.bot import handle_message, _rate_limit_state
    from datetime import datetime, timezone, timedelta

    update = _make_update("hello again")
    context = MagicMock()

    # Set the state to a past hour at the limit
    past_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    _rate_limit_state["hour"] = past_hour
    _rate_limit_state["count"] = 10  # was at limit last hour

    mock_emit = AsyncMock()

    with (
        patch.dict(os.environ, {"RATE_LIMIT_QUERIES_PER_HOUR": "5"}),
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot._emit_to_orchestrator", mock_emit),
        patch("clive_telegram.bot.sessions") as mock_sessions,
    ):
        mock_sessions.get_or_create = MagicMock(return_value=__import__("uuid").uuid4())
        await handle_message(update, context)

    # Counter reset — query should have gone through
    mock_emit.assert_called_once()
    assert mock_emit.call_args.args[0] == "query.received"


@pytest.mark.asyncio
async def test_no_rate_limit_when_env_var_unset():
    """No rate limiting when RATE_LIMIT_QUERIES_PER_HOUR is unset."""
    from clive_telegram.bot import handle_message

    update = _make_update("no limit here")
    context = MagicMock()

    mock_emit = AsyncMock()
    env = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_QUERIES_PER_HOUR"}

    with (
        patch.dict(os.environ, env, clear=True),
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot._emit_to_orchestrator", mock_emit),
        patch("clive_telegram.bot.sessions") as mock_sessions,
    ):
        mock_sessions.get_or_create = MagicMock(return_value=__import__("uuid").uuid4())
        await handle_message(update, context)

    mock_emit.assert_called_once()


# ---------------------------------------------------------------------------
# /status spend display — D-126 criterion 6
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_includes_spend_and_cap():
    """/status response includes today's spend (4dp) and daily cap. D-126 criterion 6."""
    from clive_telegram.bot import handle_status

    update = _make_update("/status")
    context = MagicMock()

    mock_orchestrator_response = {
        "doc_count": 3,
        "chunk_count": 120,
        "last_doc_name": "report.pdf",
        "last_doc_at": "2026-05-15T08:00:00",
        "last_query_at": "2026-05-15T09:30:00",
        "llm_spend_today_usd": 0.0023,
        "daily_cap_usd": 10.0,
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_orchestrator_response)

    with (
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot.httpx.AsyncClient") as mock_http,
    ):
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        await handle_status(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]

    # D-126 criterion 6: today's spend at minimum 4 decimal places
    assert "0.0023" in text, f"Expected spend '0.0023' in: {text}"
    # D-126 criterion 6: cap value present
    assert "10.0000" in text, f"Expected cap '10.0000' in: {text}"


@pytest.mark.asyncio
async def test_status_shows_no_cap_when_unset():
    """/status shows 'no cap set' when daily_cap_usd is None. D-126 criterion 6."""
    from clive_telegram.bot import handle_status

    update = _make_update("/status")
    context = MagicMock()

    mock_orchestrator_response = {
        "doc_count": 0,
        "chunk_count": 0,
        "last_doc_name": None,
        "last_doc_at": None,
        "last_query_at": None,
        "llm_spend_today_usd": 0.0,
        "daily_cap_usd": None,
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_orchestrator_response)

    with (
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot.httpx.AsyncClient") as mock_http,
    ):
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
        await handle_status(update, context)

    text = update.message.reply_text.call_args.args[0]
    assert "no cap set" in text.lower(), f"Expected 'no cap set' in: {text}"
    # Spend should show 0.0000
    assert "0.0000" in text, f"Expected '0.0000' in: {text}"
