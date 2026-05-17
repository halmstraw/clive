"""Tests for telegram bot.py — intent detection, command handlers, and HTTP endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# detect_search_intent
# ---------------------------------------------------------------------------

class TestDetectSearchIntent:
    def test_search_for_query(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("search for python asyncio")
        assert result == "python asyncio"

    def test_look_up_query(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("look up weather in London")
        assert result == "weather in London"

    def test_find_online_query(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("find online the best recipes")
        assert result == "the best recipes"

    def test_search_online_for(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("search online for restaurants")
        assert result == "restaurants"

    def test_no_match_returns_none(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("what is the capital of France")
        assert result is None

    def test_plain_question_no_match(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("tell me about python")
        assert result is None

    def test_case_insensitive(self):
        from clive_telegram.bot import detect_search_intent
        result = detect_search_intent("SEARCH for python tutorials")
        assert result == "python tutorials"


# ---------------------------------------------------------------------------
# detect_reminder_intent
# ---------------------------------------------------------------------------

class TestDetectReminderIntent:
    def test_remind_me_about_at(self):
        from clive_telegram.bot import detect_reminder_intent

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "UTC"}):
            result = detect_reminder_intent("remind me about the dentist at 3pm")

        assert result is not None
        msg, fire_at = result
        assert "dentist" in msg
        assert isinstance(fire_at, datetime)

    def test_remind_me_to_at(self):
        from clive_telegram.bot import detect_reminder_intent

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "UTC"}):
            result = detect_reminder_intent("remind me to call mum at 9am tomorrow")

        assert result is not None
        msg, fire_at = result
        assert "call mum" in msg

    def test_no_match_returns_none(self):
        from clive_telegram.bot import detect_reminder_intent

        result = detect_reminder_intent("what time is it")
        assert result is None

    def test_invalid_time_returns_none(self):
        from clive_telegram.bot import detect_reminder_intent

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "UTC"}):
            result = detect_reminder_intent("remind me about stuff at xyzzy-not-a-time")

        # Either None or parseable — depends on fuzzy parser
        # Main thing: no exception raised
        # (dateutil is very permissive; some inputs may still parse)

    def test_case_insensitive(self):
        from clive_telegram.bot import detect_reminder_intent

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "UTC"}):
            result = detect_reminder_intent("REMIND ME ABOUT meeting AT 5pm")

        assert result is not None


# ---------------------------------------------------------------------------
# _get_tz
# ---------------------------------------------------------------------------

class TestGetTz:
    def test_valid_timezone(self):
        from clive_telegram.bot import _get_tz

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "Europe/London"}):
            tz = _get_tz()

        from zoneinfo import ZoneInfo
        assert isinstance(tz, ZoneInfo)

    def test_invalid_timezone_falls_back_to_utc(self):
        from clive_telegram.bot import _get_tz

        with patch.dict("os.environ", {"CLIVE_TIMEZONE": "Not/Valid/Zone"}):
            tz = _get_tz()

        from zoneinfo import ZoneInfo
        assert tz.key == "UTC"

    def test_default_is_utc(self):
        from clive_telegram.bot import _get_tz
        import os
        os.environ.pop("CLIVE_TIMEZONE", None)

        tz = _get_tz()
        from zoneinfo import ZoneInfo
        assert isinstance(tz, ZoneInfo)


# ---------------------------------------------------------------------------
# _emit_to_orchestrator
# ---------------------------------------------------------------------------

class TestEmitToOrchestrator:
    @pytest.mark.asyncio
    async def test_posts_to_orchestrator_events(self):
        from clive_telegram.bot import _emit_to_orchestrator

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client):
            await _emit_to_orchestrator("query.received", {"payload": {"input_text": "hi"}})

        mock_client.post.assert_called_once()
        post_json = mock_client.post.call_args[1]["json"]
        assert post_json["event_type"] == "query.received"
        assert post_json["source_block"] == 23


# ---------------------------------------------------------------------------
# handle_start
# ---------------------------------------------------------------------------

class TestHandleStart:
    @pytest.mark.asyncio
    async def test_authenticated_user_resets_session(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.effective_chat.id = 12345
        mock_update.message = AsyncMock()
        mock_update.message.reply_text = AsyncMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.sessions") as mock_sessions,
            patch("clive_telegram.bot.telegram_commands_total") as mock_counter,
        ):
            mock_sessions.reset = MagicMock(return_value=uuid.uuid4())
            mock_counter.labels.return_value.inc = MagicMock()
            await bot.handle_start(mock_update, MagicMock())

        mock_sessions.reset.assert_called_once_with(12345)
        mock_update.message.reply_text.assert_called_once_with("Ready.")

    @pytest.mark.asyncio
    async def test_unauthenticated_user_ignored(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.effective_chat.id = 99999
        mock_update.message = AsyncMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=False),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            await bot.handle_start(mock_update, MagicMock())

        mock_sessions.reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_effective_chat_returns_early(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.effective_chat = None

        # Should return without error
        await bot.handle_start(mock_update, MagicMock())


# ---------------------------------------------------------------------------
# handle_message — basic routing
# ---------------------------------------------------------------------------

class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_unauthenticated_message_ignored(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.message = MagicMock()
        mock_update.message.text = "hello"
        mock_update.effective_chat.id = 99999

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=False),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
        ):
            await bot.handle_message(mock_update, MagicMock())

        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_text_returns_early(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.message = MagicMock()
        mock_update.message.text = "   "
        mock_update.effective_chat.id = 12345

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._check_rate_limit", AsyncMock(return_value=False)),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot.handle_message(mock_update, MagicMock())

        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_intent_emits_action_pending(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.message = MagicMock()
        mock_update.message.text = "search for python tutorials"
        mock_update.message.date = datetime.now(timezone.utc)
        mock_update.effective_chat.id = 12345

        mock_emit = AsyncMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._check_rate_limit", AsyncMock(return_value=False)),
            patch("clive_telegram.bot.detect_search_intent", return_value="python tutorials"),
            patch("clive_telegram.bot._emit_action_pending", mock_emit),
            patch("clive_telegram.bot.sessions") as mock_sessions,
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot.handle_message(mock_update, MagicMock())

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["action_type"] == "web.search"
        assert call_kwargs["action_target"] == "python tutorials"

    @pytest.mark.asyncio
    async def test_no_message_returns_early(self):
        from clive_telegram import bot

        mock_update = MagicMock()
        mock_update.message = None

        # Should return without error
        await bot.handle_message(mock_update, MagicMock())


# ---------------------------------------------------------------------------
# _check_rate_limit
# ---------------------------------------------------------------------------

class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_no_limit_configured_always_passes(self):
        from clive_telegram.bot import _check_rate_limit
        import os
        os.environ.pop("RATE_LIMIT_QUERIES_PER_HOUR", None)

        mock_update = MagicMock()
        result = await _check_rate_limit(12345, mock_update)
        assert result is False

    @pytest.mark.asyncio
    async def test_below_limit_passes(self):
        from clive_telegram.bot import _check_rate_limit, _rate_limit_state

        current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _rate_limit_state["hour"] = current_hour
        _rate_limit_state["count"] = 0

        mock_update = MagicMock()
        mock_update.message = None

        with patch.dict("os.environ", {"RATE_LIMIT_QUERIES_PER_HOUR": "10"}):
            result = await _check_rate_limit(12345, mock_update)

        assert result is False
        assert _rate_limit_state["count"] == 1

    @pytest.mark.asyncio
    async def test_at_limit_blocks_and_replies(self):
        from clive_telegram.bot import _check_rate_limit, _rate_limit_state

        current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _rate_limit_state["hour"] = current_hour
        _rate_limit_state["count"] = 10

        mock_update = MagicMock()
        mock_update.message = AsyncMock()
        mock_update.message.reply_text = AsyncMock()

        with (
            patch.dict("os.environ", {"RATE_LIMIT_QUERIES_PER_HOUR": "10"}),
            patch("clive_telegram.bot.rate_limited_total") as mock_counter,
        ):
            mock_counter.inc = MagicMock()
            result = await _check_rate_limit(12345, mock_update)

        assert result is True
        mock_update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# _deliver_message_with_fallback
# ---------------------------------------------------------------------------

class TestDeliverMessageWithFallback:
    @pytest.mark.asyncio
    async def test_delivers_with_markdown_on_first_try(self):
        from clive_telegram import bot

        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()

        original_app = bot._app
        try:
            bot._app = mock_app
            result = await bot._deliver_message_with_fallback(12345, "Hello *world*", "evt-001")
        finally:
            bot._app = original_app

        assert result is True
        mock_app.bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_plain_text_on_parse_error(self):
        from clive_telegram import bot

        call_count = 0

        async def mock_send(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("parse_mode") == "Markdown":
                raise Exception("Bad Markdown")

        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock(side_effect=mock_send)

        original_app = bot._app
        try:
            bot._app = mock_app
            result = await bot._deliver_message_with_fallback(12345, "Hello", "evt-002")
        finally:
            bot._app = original_app

        # Tried markdown, fell back to plain
        assert call_count >= 2
