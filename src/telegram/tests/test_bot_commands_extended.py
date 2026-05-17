"""Extended tests for telegram bot.py — more command handlers."""
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


def _make_context(args: list | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args or []
    ctx.bot = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# _emit_action_pending
# ---------------------------------------------------------------------------

class TestEmitActionPending:
    @pytest.mark.asyncio
    async def test_emits_action_pending_event(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client):
            await bot_mod._emit_action_pending(
                action_type="web.search",
                action_target="python tutorials",
                action_description="Search for python tutorials",
                conversation_id=uuid.uuid4(),
                chat_id=12345,
            )

        mock_client.post.assert_called_once()
        post_json = mock_client.post.call_args[1]["json"]
        assert post_json["event_type"] == "action.pending"
        assert post_json["payload"]["action_type"] == "web.search"

    @pytest.mark.asyncio
    async def test_includes_extra_payload(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client):
            await bot_mod._emit_action_pending(
                action_type="reminder.schedule",
                action_target="call dentist",
                action_description="Remind: call dentist",
                conversation_id=uuid.uuid4(),
                chat_id=12345,
                extra={"reminder_message": "call dentist", "fire_at": "2026-05-20T09:00:00"},
            )

        post_json = mock_client.post.call_args[1]["json"]
        assert "reminder_message" in post_json["payload"]


# ---------------------------------------------------------------------------
# handle_ingest — no document attached
# ---------------------------------------------------------------------------

class TestHandleIngest:
    @pytest.mark.asyncio
    async def test_no_document_replies_with_usage(self):
        update = _make_update()
        update.message.document = None

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_ingest(update, _make_context())

        update.message.reply_text.assert_called_once()
        assert "Send a file" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_file_too_large_rejects(self):
        update = _make_update()
        update.message.document = MagicMock()
        update.message.document.file_size = 20 * 1024 * 1024  # 20 MB > 10 MB
        update.message.document.file_name = "big.pdf"

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()),
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_ingest(update, _make_context())

        update.message.reply_text.assert_called_once()
        assert "too large" in update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_early(self):
        update = _make_update()
        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await bot_mod.handle_ingest(update, _make_context())
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_ingest(self):
        update = _make_update()
        doc = MagicMock()
        doc.file_size = 1024  # Small file
        doc.file_name = "test.pdf"
        doc.file_id = "file_id_123"
        doc.mime_type = "application/pdf"
        update.message.document = doc

        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"content"))

        ctx = _make_context()
        ctx.bot.get_file = AsyncMock(return_value=mock_file)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.upload_document", AsyncMock()),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_ingest(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "Received" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_minio_upload_failure_replies(self):
        update = _make_update()
        doc = MagicMock()
        doc.file_size = 1024
        doc.file_name = "test.pdf"
        doc.file_id = "file_id_123"
        doc.mime_type = "application/pdf"
        update.message.document = doc

        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"content"))

        ctx = _make_context()
        ctx.bot.get_file = AsyncMock(return_value=mock_file)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.upload_document", AsyncMock(side_effect=RuntimeError("bucket missing"))),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_ingest(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "bucket" in update.message.reply_text.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# handle_document_received (mobile ingest)
# ---------------------------------------------------------------------------

class TestHandleDocumentReceived:
    @pytest.mark.asyncio
    async def test_stores_pending_ingest_and_prompts(self):
        update = _make_update()
        doc = MagicMock()
        doc.file_size = 1024
        doc.file_name = "notes.pdf"
        doc.file_id = "file_123"
        doc.mime_type = "application/pdf"
        update.message.document = doc

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_document_received(update, _make_context())

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "notes.pdf" in text
        assert "/ingest_confirm" in text
        assert 12345 in bot_mod._pending_ingests

        # Cleanup
        bot_mod._pending_ingests.pop(12345, None)

    @pytest.mark.asyncio
    async def test_no_document_returns_early(self):
        update = _make_update()
        update.message.document = None

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_document_received(update, _make_context())

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_too_large_rejects(self):
        update = _make_update()
        doc = MagicMock()
        doc.file_size = 20 * 1024 * 1024  # 20 MB
        doc.file_name = "huge.pdf"
        update.message.document = doc

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_document_received(update, _make_context())

        update.message.reply_text.assert_called_once()
        assert "large" in update.message.reply_text.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# handle_ingest_confirm
# ---------------------------------------------------------------------------

class TestHandleIngestConfirm:
    @pytest.mark.asyncio
    async def test_no_pending_replies_with_message(self):
        update = _make_update()
        bot_mod._pending_ingests.pop(12345, None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_ingest_confirm(update, _make_context())

        update.message.reply_text.assert_called_once()
        assert "No pending" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_successful_confirm(self):
        update = _make_update()
        bot_mod._pending_ingests[12345] = {
            "file_id": "file_123",
            "original_filename": "doc.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
        }

        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"content"))

        ctx = _make_context()
        ctx.bot.get_file = AsyncMock(return_value=mock_file)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.upload_document", AsyncMock()),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_ingest_confirm(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "doc.pdf" in update.message.reply_text.call_args[0][0]
        assert 12345 not in bot_mod._pending_ingests

    @pytest.mark.asyncio
    async def test_download_failure_replies(self):
        update = _make_update()
        bot_mod._pending_ingests[12345] = {
            "file_id": "file_123",
            "original_filename": "doc.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
        }

        ctx = _make_context()
        ctx.bot.get_file = AsyncMock(side_effect=Exception("download error"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_ingest_confirm(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "Could not download" in update.message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# handle_delete — happy path
# ---------------------------------------------------------------------------

class TestHandleDeleteHappyPath:
    @pytest.mark.asyncio
    async def test_no_filename_shows_usage(self):
        update = _make_update()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_delete(update, _make_context(args=[]))

        update.message.reply_text.assert_called_once()
        assert "Usage" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_document_not_found_replies(self):
        update = _make_update()
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)
        )

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_delete(update, _make_context(args=["missing.pdf"]))

        update.message.reply_text.assert_called_once()
        assert "No document" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_successful_delete_emits_action_pending(self):
        update = _make_update()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"source_keys": ["uid/report.pdf"], "chunk_count": 5})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.httpx.AsyncClient", return_value=mock_client),
            patch("clive_telegram.bot._emit_to_orchestrator", AsyncMock()) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await bot_mod.handle_delete(update, _make_context(args=["report.pdf"]))

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args[0]
        assert call_args[0] == "action.pending"
        assert call_args[1]["payload"]["action_type"] == "document.delete"


# ---------------------------------------------------------------------------
# handle_confirm_delete — has pending action
# ---------------------------------------------------------------------------

class TestHandleConfirmDeleteWithPending:
    @pytest.mark.asyncio
    async def test_emits_owner_response_when_pending(self):
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
            await bot_mod.handle_confirm_delete(update, _make_context())

        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0] == "action.owner_response"
        # Cleanup
        bot_mod._pending_deletes.pop(12345, None)


# ---------------------------------------------------------------------------
# deliver_tool_updated / deliver_tool_error
# ---------------------------------------------------------------------------

class TestDeliverToolUpdated:
    @pytest.mark.asyncio
    async def test_delivers_disable_message(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        bot_mod._confirmed_tool_ops[12345] = {"tool_name": "web_search", "op": "disable", "deprecated": False}
        try:
            await bot_mod.deliver_tool_updated({}, 12345)
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "disabled" in text
            assert "web_search" in text
        finally:
            bot_mod._app = original_app
            bot_mod._confirmed_tool_ops.pop(12345, None)

    @pytest.mark.asyncio
    async def test_delivers_enable_message(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        bot_mod._confirmed_tool_ops[12345] = {"tool_name": "web_search", "op": "enable", "deprecated": False}
        try:
            await bot_mod.deliver_tool_updated({}, 12345)
            text = mock_app.bot.send_message.call_args[1]["text"]
            assert "enabled" in text
        finally:
            bot_mod._app = original_app
            bot_mod._confirmed_tool_ops.pop(12345, None)

    @pytest.mark.asyncio
    async def test_fallback_when_no_local_state(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        bot_mod._confirmed_tool_ops.pop(12345, None)  # No local state
        try:
            await bot_mod.deliver_tool_updated({"tool_name": "web_search", "operation": "disable"}, 12345)
            mock_app.bot.send_message.assert_called_once()
        finally:
            bot_mod._app = original_app


class TestDeliverToolError:
    @pytest.mark.asyncio
    async def test_delivers_error_message(self):
        original_app = bot_mod._app
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        bot_mod._app = mock_app
        try:
            await bot_mod.deliver_tool_error({}, 12345)
            mock_app.bot.send_message.assert_called_once()
        finally:
            bot_mod._app = original_app


# ---------------------------------------------------------------------------
# handle_tools
# ---------------------------------------------------------------------------

class TestHandleTools:
    @pytest.mark.asyncio
    async def test_lists_tools(self):
        update = _make_update()

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "tool_name": "web_search",
            "display_name": "Web Search",
            "version": "1.0",
            "description": "Search the web",
            "enabled": True,
            "deprecated": False,
            "deprecation_note": None,
            "health_status": "healthy",
        }.get(k, ""))

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_tools(update, _make_context())

        update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_no_tools_registered(self):
        update = _make_update()

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_tools(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "No tools" in text

    @pytest.mark.asyncio
    async def test_db_error_shows_unavailable(self):
        update = _make_update()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(side_effect=Exception("db down"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            mock_ctr.labels.return_value.inc = MagicMock()
            await bot_mod.handle_tools(update, _make_context())

        update.message.reply_text.assert_called_once()
