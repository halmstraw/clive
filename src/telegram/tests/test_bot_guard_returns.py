"""Tests for guard returns in bot.py — covers 'if not update.message' return paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clive_telegram import bot as bot_mod


def _make_no_message_update() -> MagicMock:
    update = MagicMock()
    update.message = None
    update.effective_chat = None
    return update


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.args = []
    return ctx


# ---------------------------------------------------------------------------
# update.message = None guard returns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_cancel_delete_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_cancel_delete(update, _make_context())


@pytest.mark.asyncio
async def test_handle_confirm_action_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_confirm_action(update, _make_context())


@pytest.mark.asyncio
async def test_handle_cancel_action_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_cancel_action(update, _make_context())


@pytest.mark.asyncio
async def test_handle_document_received_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_document_received(update, _make_context())


@pytest.mark.asyncio
async def test_handle_ingest_confirm_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_ingest_confirm(update, _make_context())


@pytest.mark.asyncio
async def test_handle_list_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_list(update, _make_context())


@pytest.mark.asyncio
async def test_handle_status_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_status(update, _make_context())


@pytest.mark.asyncio
async def test_handle_tools_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_tools(update, _make_context())


@pytest.mark.asyncio
async def test_handle_tool_disable_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_tool_disable(update, _make_context())


@pytest.mark.asyncio
async def test_handle_tool_enable_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_tool_enable(update, _make_context())


@pytest.mark.asyncio
async def test_handle_activate_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_activate(update, _make_context())


@pytest.mark.asyncio
async def test_handle_confirm_activate_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_confirm_activate(update, _make_context())


@pytest.mark.asyncio
async def test_handle_ingest_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_ingest(update, _make_context())


@pytest.mark.asyncio
async def test_handle_delete_no_message():
    update = _make_no_message_update()
    await bot_mod.handle_delete(update, _make_context())


@pytest.mark.asyncio
async def test_whoami_command_no_message():
    update = _make_no_message_update()
    await bot_mod.whoami_command(update, _make_context())


# ---------------------------------------------------------------------------
# handle_activate — invalid args (lines 465-469)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_activate_invalid_doc_type():
    """handle_activate with invalid document_type shows usage."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 12345

    ctx = MagicMock()
    ctx.args = ["invalid_type"]

    with (
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
    ):
        mock_ctr.labels.return_value.inc = MagicMock()
        await bot_mod.handle_activate(update, ctx)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text or "activate" in text.lower()


@pytest.mark.asyncio
async def test_handle_activate_no_args():
    """handle_activate with no args shows usage."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 12345

    ctx = MagicMock()
    ctx.args = []

    with (
        patch("clive_telegram.bot.is_authenticated", return_value=True),
        patch("clive_telegram.bot.telegram_commands_total") as mock_ctr,
    ):
        mock_ctr.labels.return_value.inc = MagicMock()
        await bot_mod.handle_activate(update, ctx)

    update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# handle_start — internal code (lines 361-369)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_start_no_effective_chat():
    update = MagicMock()
    update.effective_chat = None
    update.message = None
    await bot_mod.handle_start(update, _make_context())  # Should return early


# ---------------------------------------------------------------------------
# _send_message (line 378)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_message_calls_bot_send():
    original_app = bot_mod._app
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    bot_mod._app = mock_app
    try:
        await bot_mod._send_message(12345, "Test text", "Markdown")
        mock_app.bot.send_message.assert_called_once_with(
            chat_id=12345, text="Test text", parse_mode="Markdown"
        )
    finally:
        bot_mod._app = original_app


@pytest.mark.asyncio
async def test_send_message_no_parse_mode():
    original_app = bot_mod._app
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    bot_mod._app = mock_app
    try:
        await bot_mod._send_message(12345, "Plain text", None)
        # send_message called without parse_mode
        call_kwargs = mock_app.bot.send_message.call_args[1]
        assert "parse_mode" not in call_kwargs
    finally:
        bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_response — all delivery attempts fail (line 428)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_response_all_attempts_fail():
    original_app = bot_mod._app
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock(side_effect=Exception("send fail"))
    bot_mod._app = mock_app

    eid = "evt-test-fallback"
    bot_mod._rendered_event_ids.discard(eid)
    try:
        # Should not raise even when all delivery attempts fail
        await bot_mod.deliver_response(
            {"event_id": eid, "response_text": "Hello"},
            chat_id=12345,
        )
    finally:
        bot_mod._app = original_app
        bot_mod._rendered_event_ids.discard(eid)


# ---------------------------------------------------------------------------
# deliver_ingest_status — more paths (lines 775, 779)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_ingest_status_rejection_unknown_reason():
    original_app = bot_mod._app
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    bot_mod._app = mock_app
    try:
        await bot_mod.deliver_ingest_status(
            {"event_type": "ingest.rejected", "source_key": "uid/file.pdf", "reason": "unknown_reason"},
            chat_id=12345,
        )
        text = mock_app.bot.send_message.call_args[1]["text"]
        assert "failed" in text.lower() or "unknown_reason" in text
    finally:
        bot_mod._app = original_app


# ---------------------------------------------------------------------------
# deliver_deletion_result — no-op event type (line 1019)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_deletion_result_not_found_without_suppress():
    """deletion.not_found sends a 'not found' message."""
    original_app = bot_mod._app
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    bot_mod._app = mock_app
    try:
        await bot_mod.deliver_deletion_result(
            {"event_type": "deletion.not_found", "filename": "ghost.pdf"},
            chat_id=12345,
        )
        text = mock_app.bot.send_message.call_args[1]["text"]
        assert "ghost.pdf" in text
    finally:
        bot_mod._app = original_app
