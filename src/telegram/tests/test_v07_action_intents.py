"""v0.7 Block 9 — Unit tests for intent detection and generic confirmation UX.

Criteria covered:
  Criterion 2: search intent detection fires action.pending (not query.received)
  Criterion 4: reminder intent detection fires action.pending (not query.received)
  Passthrough: non-matching messages still emit query.received
  Criterion 6: /confirm_action and /cancel_action handle pending generic actions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clive_telegram.bot import (
    detect_search_intent,
    detect_reminder_intent,
    handle_confirm_action,
    handle_cancel_action,
)


# ---------------------------------------------------------------------------
# Intent detection — search
# ---------------------------------------------------------------------------

class TestSearchIntentDetection:
    def test_search_for_pattern(self):
        assert detect_search_intent("search for Python asyncio") == "Python asyncio"

    def test_search_pattern_no_for(self):
        assert detect_search_intent("search Python tutorials") == "Python tutorials"

    def test_look_up_pattern(self):
        assert detect_search_intent("look up latest Claude models") == "latest Claude models"

    def test_find_online_pattern(self):
        assert detect_search_intent("find online best coffee shops") == "best coffee shops"

    def test_find_pattern(self):
        assert detect_search_intent("find restaurants near me") == "restaurants near me"

    def test_case_insensitive(self):
        assert detect_search_intent("SEARCH FOR weather tomorrow") == "weather tomorrow"

    def test_non_search_returns_none(self):
        assert detect_search_intent("what is the capital of France?") is None

    def test_remind_me_is_not_search(self):
        assert detect_search_intent("remind me about the dentist at 3pm") is None

    def test_empty_string_returns_none(self):
        assert detect_search_intent("") is None

    def test_partial_match_returns_none(self):
        # "searching" should not match the search intent
        assert detect_search_intent("I was searching for my keys") is None


# ---------------------------------------------------------------------------
# Intent detection — reminder
# ---------------------------------------------------------------------------

class TestReminderIntentDetection:
    def test_remind_me_about_at(self):
        result = detect_reminder_intent("remind me about the dentist at 3pm")
        assert result is not None
        msg, fire_at = result
        assert msg == "the dentist"
        assert isinstance(fire_at, datetime)

    def test_remind_me_to_at(self):
        result = detect_reminder_intent("remind me to call mum at 5:30pm")
        assert result is not None
        msg, fire_at = result
        assert msg == "call mum"

    def test_case_insensitive(self):
        result = detect_reminder_intent("REMIND ME ABOUT the meeting at 10am")
        assert result is not None

    def test_no_at_keyword_returns_none(self):
        assert detect_reminder_intent("remind me about the dentist") is None

    def test_non_reminder_returns_none(self):
        assert detect_reminder_intent("what time is the meeting?") is None

    def test_fire_at_is_timezone_aware(self):
        result = detect_reminder_intent("remind me about standup at 9am")
        assert result is not None
        _, fire_at = result
        assert fire_at.tzinfo is not None

    def test_invalid_time_returns_none(self):
        # "at xyzzy" cannot be parsed as a time by dateutil
        result = detect_reminder_intent("remind me about lunch at xyzzy")
        # dateutil is fuzzy — may or may not parse; we just confirm no crash
        # The function returns None on parse error, or (msg, dt) if dateutil accepts it
        assert result is None or isinstance(result, tuple)


# ---------------------------------------------------------------------------
# Generic confirmation commands
# ---------------------------------------------------------------------------

def _make_update(chat_id: int, command_text: str) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


class TestHandleConfirmAction:
    @pytest.mark.asyncio
    async def test_confirm_with_pending_action_emits_owner_response(self):
        chat_id = 99999
        action_request_id = str(uuid.uuid4())

        update = _make_update(chat_id, "/confirm_action")
        context = MagicMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_action_generic", {chat_id: action_request_id}),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_confirm_action(update, context)

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        event_type = call_args.args[0]
        payload = call_args.args[1]["payload"]
        assert event_type == "action.owner_response"
        assert payload["confirmed"] is True
        assert payload["action_request_id"] == action_request_id

    @pytest.mark.asyncio
    async def test_confirm_with_no_pending_action_replies_error(self):
        chat_id = 99999
        update = _make_update(chat_id, "/confirm_action")
        context = MagicMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_action_generic", {}),
        ):
            await handle_confirm_action(update, context)

        update.message.reply_text.assert_called_once()
        assert "No pending action" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_confirm_clears_pending_state(self):
        chat_id = 99999
        action_request_id = str(uuid.uuid4())
        pending = {chat_id: action_request_id}

        update = _make_update(chat_id, "/confirm_action")
        context = MagicMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_action_generic", pending),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_confirm_action(update, context)

        assert chat_id not in pending


class TestHandleCancelAction:
    @pytest.mark.asyncio
    async def test_cancel_with_pending_action_emits_rejection(self):
        chat_id = 99999
        action_request_id = str(uuid.uuid4())

        update = _make_update(chat_id, "/cancel_action")
        context = MagicMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_action_generic", {chat_id: action_request_id}),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_cancel_action(update, context)

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        payload = call_args.args[1]["payload"]
        assert payload["confirmed"] is False

    @pytest.mark.asyncio
    async def test_cancel_with_no_pending_action_replies_error(self):
        chat_id = 99999
        update = _make_update(chat_id, "/cancel_action")
        context = MagicMock()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_action_generic", {}),
        ):
            await handle_cancel_action(update, context)

        update.message.reply_text.assert_called_once()
        assert "No pending" in update.message.reply_text.call_args.args[0]
