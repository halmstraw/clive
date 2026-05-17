"""Edge case tests for bot.py command handlers — covering remaining missing lines."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clive_telegram import bot as bot_mod


def _make_update(chat_id: int = 12345) -> MagicMock:
    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = "test"
    update.message.date = datetime.now(timezone.utc)
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = chat_id
    return update


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.args = []
    return ctx


# ---------------------------------------------------------------------------
# handle_message — reminder intent routing (lines 292-302)
# ---------------------------------------------------------------------------

class TestHandleMessageReminderIntent:
    @pytest.mark.asyncio
    async def test_reminder_intent_emits_action_pending(self):
        update = _make_update()
        update.message.text = "remind me about the dentist at 3pm"

        from datetime import datetime, timezone
        fire_at = datetime.now(timezone.utc)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._check_rate_limit", AsyncMock(return_value=False)),
            patch("clive_telegram.bot.detect_search_intent", return_value=None),
            patch("clive_telegram.bot.detect_reminder_intent", return_value=("dentist", fire_at)),
            patch("clive_telegram.bot._emit_action_pending", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_message(update, _make_context())

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["action_type"] == "reminder.schedule"
        assert call_kwargs["action_target"] == "dentist"


# ---------------------------------------------------------------------------
# handle_cancel_delete — with pending action (line 912)
# ---------------------------------------------------------------------------

class TestHandleCancelDeleteWithPending:
    @pytest.mark.asyncio
    async def test_emits_owner_response_with_rejected(self):
        update = _make_update()
        bot_mod._pending_deletes[12345] = "req-001"

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_cancel_delete(update, _make_context())

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args[0]
        assert call_args[1]["payload"]["confirmed"] is False
        # Cleanup
        bot_mod._pending_deletes.pop(12345, None)


# ---------------------------------------------------------------------------
# handle_confirm_action — with pending action (line 1166)
# ---------------------------------------------------------------------------

class TestHandleConfirmActionWithPending:
    @pytest.mark.asyncio
    async def test_emits_confirmed_response(self):
        update = _make_update()
        bot_mod._pending_action_generic[12345] = "req-search-001"

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_confirm_action(update, _make_context())

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args[0]
        assert call_args[1]["payload"]["confirmed"] is True
        update.message.reply_text.assert_called_once_with("Confirmed.")


# ---------------------------------------------------------------------------
# handle_cancel_action — with pending action (line 1235)
# ---------------------------------------------------------------------------

class TestHandleCancelActionWithPending:
    @pytest.mark.asyncio
    async def test_emits_rejected_response(self):
        update = _make_update()
        bot_mod._pending_action_generic[12345] = "req-search-002"

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_cancel_action(update, _make_context())

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args[0]
        assert call_args[1]["payload"]["confirmed"] is False


# ---------------------------------------------------------------------------
# handle_bad — retrieval missing event_id (lines 1073, 1093-1096)
# ---------------------------------------------------------------------------

class TestHandleBadEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_event_id_in_last_retrieval(self):
        update = _make_update()
        # Last retrieval has no event_id
        bot_mod._last_retrieval[12345] = {"event_id": "", "chunk_ids": [], "conversation_id": None}

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_bad(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "No recent retrieval" in text

        # Cleanup
        bot_mod._last_retrieval.pop(12345, None)

    @pytest.mark.asyncio
    async def test_handle_bad_with_valid_retrieval(self):
        update = _make_update()
        eid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        bot_mod._last_retrieval[12345] = {
            "event_id": eid,
            "chunk_ids": [str(uuid.uuid4())],
            "conversation_id": cid,
        }

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()),
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_bad(update, _make_context())

        # Should have written feedback
        mock_conn.execute.assert_called()

        # Cleanup
        bot_mod._last_retrieval.pop(12345, None)


# ---------------------------------------------------------------------------
# handle_tools — unauthenticated (line 1630)
# ---------------------------------------------------------------------------

class TestHandleToolsUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_tools(update, _make_context())
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# handle_tool_disable — unauthenticated (line 1676)
# ---------------------------------------------------------------------------

class TestHandleToolDisableUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_tool_disable(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self):
        update = _make_update()
        ctx = MagicMock()
        ctx.args = []

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_tool_disable(update, ctx)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "tool" in text.lower()


# ---------------------------------------------------------------------------
# handle_tool_enable — unauthenticated (line 1760)
# ---------------------------------------------------------------------------

class TestHandleToolEnableUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_tool_enable(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self):
        update = _make_update()
        ctx = MagicMock()
        ctx.args = []

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_tool_enable(update, ctx)

        update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# deliver_tool_updated — with deprecated tool (line 1888)
# ---------------------------------------------------------------------------

class TestDeliverToolUpdatedDeprecated:
    @pytest.mark.asyncio
    async def test_delivers_deprecated_enable_message(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        bot_mod._confirmed_tool_ops[12345] = {
            "tool_name": "old_tool",
            "op": "enable",
            "deprecated": True,
        }
        try:
            await bot_mod.deliver_tool_updated({}, 12345)
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "deprecated" in text.lower()
        finally:
            bot_mod._app = original_app
            bot_mod._confirmed_tool_ops.pop(12345, None)

    @pytest.mark.asyncio
    async def test_delivers_unknown_op_message(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        bot_mod._confirmed_tool_ops[12345] = {
            "tool_name": "my_tool",
            "op": "unknown_op",
            "deprecated": False,
        }
        try:
            await bot_mod.deliver_tool_updated({}, 12345)
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "my_tool" in text
        finally:
            bot_mod._app = original_app
            bot_mod._confirmed_tool_ops.pop(12345, None)


# ---------------------------------------------------------------------------
# handle_delete — general exception path (lines 813-815)
# ---------------------------------------------------------------------------

class TestHandleDeleteExceptionPath:
    @pytest.mark.asyncio
    async def test_general_exception_shows_error_message(self):
        update = _make_update()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_delete(update, MagicMock(args=["report.pdf"]))

        text = update.message.reply_text.call_args[0][0]
        assert "Could not" in text


# ---------------------------------------------------------------------------
# handle_list / handle_status — unauthenticated (lines 1435, 1484)
# ---------------------------------------------------------------------------

class TestHandleListUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_list(update, _make_context())
        update.message.reply_text.assert_not_called()


class TestHandleStatusUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_status(update, _make_context())
        update.message.reply_text.assert_not_called()
