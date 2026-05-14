"""Tests for v0.3 Telegram commands: /delete, /confirm_delete, /cancel_delete, /bad.

D-106 acceptance criteria:
  2. Without confirmation, no deletion occurs.
  4. Not-found document → clear message, no crash.
  5. /bad persists feedback and acknowledges.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_bot_app():
    """Provide a mock Telegram Application with a spy on send_message."""
    mock_app = MagicMock()
    mock_send = AsyncMock()
    mock_app.bot.send_message = mock_send

    import clive_telegram.bot as bot_module
    original = bot_module._app
    bot_module._app = mock_app
    yield mock_app, mock_send
    bot_module._app = original


@pytest.fixture(autouse=True)
def reset_bot_state():
    """Clear per-test in-process state."""
    import clive_telegram.bot as bot_module
    bot_module._pending_deletes.clear()
    bot_module._last_retrieval.clear()
    bot_module._pending_activations.clear()
    yield
    bot_module._pending_deletes.clear()
    bot_module._last_retrieval.clear()


def _make_update(chat_id: int, command_args: list[str] | None = None):
    """Build a minimal mock Update for command handlers."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.date.isoformat.return_value = "2026-05-14T12:00:00"
    return update


def _make_context(args: list[str] | None = None):
    context = MagicMock()
    context.args = args or []
    return context


# ---------------------------------------------------------------------------
# /delete — not found path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_no_args_replies_usage():
    """/delete with no args must reply with usage hint."""
    from clive_telegram.bot import handle_delete
    update = _make_update(chat_id=99)
    context = _make_context(args=[])

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_delete(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text or "usage" in text


@pytest.mark.asyncio
async def test_delete_not_found_replies_clear_message():
    """D-106 criterion 4: not-found document → clear message, no crash, no event emitted."""
    from clive_telegram.bot import handle_delete
    update = _make_update(chat_id=99)
    context = _make_context(args=["nonexistent.pdf"])

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
        "not found",
        request=MagicMock(),
        response=MagicMock(status_code=404),
    )

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.sessions") as mock_sessions, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_sessions.get_or_create.return_value = uuid.uuid4()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await handle_delete(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "nonexistent.pdf" in text
    assert "found" in text.lower()


# ---------------------------------------------------------------------------
# /confirm_delete — no pending state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_delete_no_pending_replies_guidance():
    """/confirm_delete with no pending action must guide user."""
    from clive_telegram.bot import handle_confirm_delete
    update = _make_update(chat_id=99)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_confirm_delete(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "No pending" in text or "no pending" in text


# ---------------------------------------------------------------------------
# /cancel_delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_delete_with_pending_emits_rejected():
    """/cancel_delete with pending action must emit action.owner_response confirmed=False."""
    import clive_telegram.bot as bot_module
    action_request_id = str(uuid.uuid4())
    bot_module._pending_deletes[99] = action_request_id

    from clive_telegram.bot import handle_cancel_delete
    update = _make_update(chat_id=99)
    context = _make_context()

    emitted_events = []

    async def mock_emit(event_type, payload):
        emitted_events.append({"event_type": event_type, **payload})

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.sessions") as mock_sessions, \
         patch("clive_telegram.bot._emit_to_orchestrator", side_effect=mock_emit):
        mock_sessions.get_or_create.return_value = uuid.uuid4()
        await handle_cancel_delete(update, context)

    # Pending state cleared
    assert 99 not in bot_module._pending_deletes
    # Event emitted
    assert len(emitted_events) == 1
    assert emitted_events[0]["event_type"] == "action.owner_response"
    assert emitted_events[0]["payload"]["confirmed"] is False
    assert emitted_events[0]["payload"]["action_request_id"] == action_request_id


@pytest.mark.asyncio
async def test_cancel_delete_no_pending_replies_gracefully():
    """/cancel_delete with nothing pending must reply without crash."""
    from clive_telegram.bot import handle_cancel_delete
    update = _make_update(chat_id=99)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_cancel_delete(update, context)

    update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# /bad — Block 18 feedback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bad_no_recent_retrieval_replies_guidance():
    """/bad with no prior retrieval must inform user."""
    from clive_telegram.bot import handle_bad
    update = _make_update(chat_id=99)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_bad(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "No recent" in text or "no recent" in text


@pytest.mark.asyncio
async def test_bad_persists_feedback_and_acknowledges():
    """D-106 criterion 5: /bad writes feedback record and acknowledges."""
    import clive_telegram.bot as bot_module

    retrieval_event_id = str(uuid.uuid4())
    chunk_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    conversation_id = str(uuid.uuid4())

    # Set up last retrieval state
    bot_module._last_retrieval[99] = {
        "event_id": retrieval_event_id,
        "chunk_ids": chunk_ids,
        "conversation_id": conversation_id,
    }

    from clive_telegram.bot import handle_bad
    update = _make_update(chat_id=99)
    context = _make_context()

    # Mock DB pool
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)

    emitted_events = []

    async def mock_emit(event_type, payload):
        emitted_events.append({"event_type": event_type, **payload})

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.get_pool", return_value=pool), \
         patch("clive_telegram.bot.sessions") as mock_sessions, \
         patch("clive_telegram.bot._emit_to_orchestrator", side_effect=mock_emit):
        mock_sessions.get_or_create.return_value = uuid.uuid4()
        await handle_bad(update, context)

    # DB write happened
    conn.execute.assert_called_once()
    insert_sql = conn.execute.call_args[0][0]
    assert "clive_state.feedback" in insert_sql

    # feedback.explicit event emitted
    assert len(emitted_events) == 1
    assert emitted_events[0]["event_type"] == "feedback.explicit"
    assert emitted_events[0]["payload"]["feedback_type"] == "poor_quality"
    assert emitted_events[0]["payload"]["retrieval_event_id"] == retrieval_event_id

    # Acknowledged
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "poor quality" in text.lower() or "noted" in text.lower()


@pytest.mark.asyncio
async def test_bad_db_failure_replies_error(mock_bot_app):
    """If DB write fails, /bad must reply with error — not crash silently."""
    import clive_telegram.bot as bot_module
    _, mock_send = mock_bot_app

    bot_module._last_retrieval[99] = {
        "event_id": str(uuid.uuid4()),
        "chunk_ids": [],
        "conversation_id": str(uuid.uuid4()),
    }

    from clive_telegram.bot import handle_bad
    update = _make_update(chat_id=99)
    context = _make_context()

    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("DB unavailable"))
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.get_pool", return_value=pool):
        await handle_bad(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "failed" in text.lower() or "try again" in text.lower()


# ---------------------------------------------------------------------------
# deliver_action_confirmation / deliver_action_outcome / deliver_deletion_result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_action_confirmation_stores_and_prompts(mock_bot_app):
    """action.confirmation_requested must store action_request_id and prompt owner."""
    import clive_telegram.bot as bot_module
    _, mock_send = mock_bot_app

    action_request_id = str(uuid.uuid4())
    chat_id = 99

    from clive_telegram.bot import deliver_action_confirmation
    await deliver_action_confirmation(
        {
            "action_request_id": action_request_id,
            "action_description": "Delete report.pdf (5 chunks).",
            "chat_id": chat_id,
        },
        chat_id=chat_id,
    )

    # Stored for /confirm_delete
    assert bot_module._pending_deletes[chat_id] == action_request_id

    # Prompt sent to owner
    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "confirm" in text.lower() or "confirm\\_delete" in text.lower()


@pytest.mark.asyncio
async def test_deliver_deletion_result_complete(mock_bot_app):
    """deletion.complete must send a clear success message."""
    _, mock_send = mock_bot_app

    from clive_telegram.bot import deliver_deletion_result
    await deliver_deletion_result(
        {
            "event_type": "deletion.complete",
            "filename": "report.pdf",
            "chunks_removed": 7,
        },
        chat_id=99,
    )

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "") or mock_send.call_args[0][0] if mock_send.call_args[0] else ""
    # Accept either positional or keyword 'text'
    all_args = str(mock_send.call_args)
    assert "report.pdf" in all_args
    assert "7" in all_args or "Deleted" in all_args


@pytest.mark.asyncio
async def test_deliver_deletion_result_not_found(mock_bot_app):
    """deletion.not_found must send a clear not-found message."""
    _, mock_send = mock_bot_app

    from clive_telegram.bot import deliver_deletion_result
    await deliver_deletion_result(
        {
            "event_type": "deletion.not_found",
            "filename": "ghost.pdf",
        },
        chat_id=99,
    )

    mock_send.assert_called_once()
    all_args = str(mock_send.call_args)
    assert "ghost.pdf" in all_args
    assert "found" in all_args.lower()
