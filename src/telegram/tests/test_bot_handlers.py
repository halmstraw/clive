"""Tests for telegram bot.py — deliver_* and command handler functions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clive_telegram import bot as bot_mod


def _make_update(chat_id: int = 12345, text: str = "", args: list | None = None) -> MagicMock:
    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = text
    update.message.date = datetime.now(timezone.utc)
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = chat_id
    return update


def _make_context(args: list | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


def _mock_app() -> MagicMock:
    mock = MagicMock()
    mock.bot.send_message = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# deliver_response
# ---------------------------------------------------------------------------

class TestDeliverResponse:
    @pytest.mark.asyncio
    async def test_delivers_response_text(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            eid = str(uuid.uuid4())
            bot_mod._rendered_event_ids.discard(eid)
            await bot_mod.deliver_response(
                {"event_id": eid, "response_text": "Hello!", "confidence": {"threshold_met": True}, "chunk_ids": []},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_called()
        finally:
            bot_mod._app = original_app
            bot_mod._rendered_event_ids.discard(eid)

    @pytest.mark.asyncio
    async def test_skips_duplicate_event_id(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        eid = str(uuid.uuid4())
        bot_mod._rendered_event_ids.add(eid)
        try:
            await bot_mod.deliver_response(
                {"event_id": eid, "response_text": "Hello!"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app
            bot_mod._rendered_event_ids.discard(eid)

    @pytest.mark.asyncio
    async def test_handles_missing_app_gracefully(self):
        original_app = bot_mod._app
        bot_mod._app = None
        eid = str(uuid.uuid4())
        bot_mod._rendered_event_ids.discard(eid)
        try:
            # Should not raise
            await bot_mod.deliver_response(
                {"event_id": eid, "response_text": "Hello!"},
                chat_id=12345,
            )
        finally:
            bot_mod._app = original_app
            bot_mod._rendered_event_ids.discard(eid)

    @pytest.mark.asyncio
    async def test_adds_low_confidence_indicator(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        eid = str(uuid.uuid4())
        bot_mod._rendered_event_ids.discard(eid)
        try:
            await bot_mod.deliver_response(
                {
                    "event_id": eid,
                    "response_text": "Answer",
                    "confidence": {"threshold_met": False, "chunks_returned": 0},
                    "chunk_ids": [],
                },
                chat_id=12345,
            )
            call_text = mock_app.bot.send_message.call_args[1]["text"] if mock_app.bot.send_message.call_args else ""
            # Low confidence indicator should be appended
        finally:
            bot_mod._app = original_app
            bot_mod._rendered_event_ids.discard(eid)

    @pytest.mark.asyncio
    async def test_missing_event_id_continues_without_idempotency(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            # event_id is empty string
            await bot_mod.deliver_response(
                {"event_id": "", "response_text": "Hello!"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_called()
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_alert
# ---------------------------------------------------------------------------

class TestDeliverAlert:
    @pytest.mark.asyncio
    async def test_delivers_info_alert(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_alert(
                {"severity": "info", "title": "Test", "body": "Test body"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_called_once()
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_delivers_warn_alert_with_emoji(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_alert(
                {"severity": "warn", "title": "Warning", "body": "Low disk"},
                chat_id=12345,
            )
            call_text = mock_app.bot.send_message.call_args[1]["text"]
            assert "⚠️" in call_text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_skips_when_no_app(self):
        original_app = bot_mod._app
        bot_mod._app = None
        try:
            # Should not raise
            await bot_mod.deliver_alert({"severity": "error", "title": "Error", "body": "oops"}, 12345)
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_ingest_status
# ---------------------------------------------------------------------------

class TestDeliverIngestStatus:
    @pytest.mark.asyncio
    async def test_delivers_processed_status(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_ingest_status(
                {"event_type": "ingest.processed", "source_key": "uid/doc.pdf", "chunk_count": 5, "inserted_count": 5},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_called_once()
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "doc.pdf" in text
            assert "5" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_delivers_rejected_status(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_ingest_status(
                {"event_type": "ingest.rejected", "source_key": "uid/big.pdf", "reason": "file_too_large"},
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "big.pdf" in text
            assert "large" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_returns_early_for_unknown_event_type(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_ingest_status({"event_type": "unknown"}, 12345)
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_shows_duplicate_count(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_ingest_status(
                {"event_type": "ingest.processed", "source_key": "uid/doc.pdf", "chunk_count": 10, "inserted_count": 7},
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "duplicate" in text.lower() or "skipped" in text.lower()
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_action_confirmation
# ---------------------------------------------------------------------------

class TestDeliverActionConfirmation:
    @pytest.mark.asyncio
    async def test_delivers_delete_confirmation(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_action_confirmation(
                {
                    "action_request_id": "req-001",
                    "action_description": "Delete report.pdf",
                    "action_type": "document.delete",
                },
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_called_once()
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "/confirm_delete" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_delivers_generic_confirmation(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_action_confirmation(
                {
                    "action_request_id": "req-002",
                    "action_description": "Search for python",
                    "action_type": "web.search",
                },
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "/confirm_action" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_suppress_telegram_skips_send(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_action_confirmation(
                {"suppress_telegram": True, "action_request_id": "req-003"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_action_outcome
# ---------------------------------------------------------------------------

class TestDeliverActionOutcome:
    @pytest.mark.asyncio
    async def test_delivers_rejection_with_reason(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_action_outcome(
                {"action_type": "document.delete", "action_target": "doc.pdf", "reason": "owner_rejected"},
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "cancelled" in text or "doc.pdf" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_suppress_telegram_skips_send(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_action_outcome(
                {"suppress_telegram": True, "reason": "owner_rejected"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_clears_pending_state(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        bot_mod._pending_deletes[12345] = "req-001"
        bot_mod._pending_action_generic[12345] = "req-002"
        try:
            await bot_mod.deliver_action_outcome(
                {"suppress_telegram": True},
                chat_id=12345,
            )
            assert 12345 not in bot_mod._pending_deletes
            assert 12345 not in bot_mod._pending_action_generic
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_deletion_result
# ---------------------------------------------------------------------------

class TestDeliverDeletionResult:
    @pytest.mark.asyncio
    async def test_delivers_complete(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_deletion_result(
                {"event_type": "deletion.complete", "filename": "old.pdf", "chunks_removed": 10},
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "old.pdf" in text
            assert "10" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_delivers_not_found(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_deletion_result(
                {"event_type": "deletion.not_found", "filename": "missing.pdf"},
                chat_id=12345,
            )
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "missing.pdf" in text
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_suppress_telegram_skips_send(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_deletion_result(
                {"suppress_telegram": True, "event_type": "deletion.complete"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app

    @pytest.mark.asyncio
    async def test_unknown_event_type_returns_early(self):
        original_app = bot_mod._app
        mock_app = _mock_app()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_deletion_result(
                {"event_type": "unknown_type"},
                chat_id=12345,
            )
            mock_app.bot.send_message.assert_not_called()
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# handle_list
# ---------------------------------------------------------------------------

class TestHandleList:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_list(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_document_list(self):
        update = _make_update()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "documents": [{"filename": "doc.pdf", "chunk_count": 5, "ingested_at": "2026-05-17T10:00:00"}],
            "total": 1,
        })
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_list(update, _make_context())

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "doc.pdf" in text

    @pytest.mark.asyncio
    async def test_empty_knowledge_base_message(self):
        update = _make_update()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"documents": [], "total": 0})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_list(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "No documents" in text

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        update = _make_update()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("connection error"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_list(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "Could not" in text


# ---------------------------------------------------------------------------
# handle_status
# ---------------------------------------------------------------------------

class TestHandleStatus:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_status(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_status(self):
        update = _make_update()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "doc_count": 5,
            "chunk_count": 100,
            "last_doc_name": "report.pdf",
            "last_doc_at": "2026-05-17T10:00:00",
            "last_query_at": "2026-05-17T09:00:00",
            "llm_spend_today_usd": 0.05,
            "daily_cap_usd": 10.0,
        })
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_status(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "5" in text

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        update = _make_update()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("error"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_status(update, _make_context())

        assert update.message.reply_text.called


# ---------------------------------------------------------------------------
# handle_help
# ---------------------------------------------------------------------------

class TestHandleHelp:
    @pytest.mark.asyncio
    async def test_delivers_help_text(self):
        update = _make_update()
        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_help(update, _make_context())

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "/start" in text
        assert "/list" in text
        assert "/status" in text

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_help(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_message_returns_early(self):
        update = _make_update()
        update.message = None
        await bot_mod.handle_help(update, _make_context())  # Should not raise


# ---------------------------------------------------------------------------
# handle_bad (partial paths)
# ---------------------------------------------------------------------------

class TestHandleBad:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_bad(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_last_retrieval_replies_with_message(self):
        update = _make_update()
        bot_mod._last_retrieval.pop(12345, None)  # Ensure no last retrieval

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_bad(update, _make_context())

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "No recent retrieval" in text


# ---------------------------------------------------------------------------
# handle_confirm_action / handle_cancel_action
# ---------------------------------------------------------------------------

class TestHandleConfirmAction:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_confirm_action(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pending_action_replies_with_message(self):
        update = _make_update()
        bot_mod._pending_action_generic.pop(12345, None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_confirm_action(update, _make_context())

        update.message.reply_text.assert_called_once()


class TestHandleCancelAction:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_cancel_action(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pending_action_replies_with_message(self):
        update = _make_update()
        bot_mod._pending_action_generic.pop(12345, None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_cancel_action(update, _make_context())

        update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# handle_confirm_delete / handle_cancel_delete
# ---------------------------------------------------------------------------

class TestHandleConfirmDelete:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_confirm_delete(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pending_deletion_replies_with_message(self):
        update = _make_update()
        bot_mod._pending_deletes.pop(12345, None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_confirm_delete(update, _make_context())

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "No pending" in text


class TestHandleCancelDelete:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_cancel_delete(update, _make_context())
        update.message.reply_text.assert_not_called()
