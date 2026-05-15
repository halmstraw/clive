"""Tests for v0.4 Telegram commands: mobile ingest, /list, /status.

D-113/D-116 acceptance criteria:
  2. Mobile ingest: document received → prompt → /ingest_confirm → ingest.
  3. Desktop ingest (/ingest caption) unchanged.
  4. /list returns documents or empty message.
  7. /status returns summary.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_bot_state():
    """Clear per-test in-process state including v0.4 additions."""
    import clive_telegram.bot as bot_module
    bot_module._pending_deletes.clear()
    bot_module._pending_ingests.clear()
    bot_module._last_retrieval.clear()
    bot_module._pending_activations.clear()
    yield
    bot_module._pending_deletes.clear()
    bot_module._pending_ingests.clear()
    bot_module._last_retrieval.clear()


def _make_update(chat_id: int = 99, has_document: bool = False,
                 filename: str = "test.pdf", file_size: int = 1024,
                 mime_type: str = "application/pdf"):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.date.isoformat.return_value = "2026-05-15T10:00:00"

    if has_document:
        doc = MagicMock()
        doc.file_id = "tg_file_id_123"
        doc.file_name = filename
        doc.file_size = file_size
        doc.mime_type = mime_type
        update.message.document = doc
    else:
        update.message.document = None

    return update


def _make_context():
    context = MagicMock()
    context.args = []
    context.bot = AsyncMock()
    return context


# ---------------------------------------------------------------------------
# handle_document_received — mobile ingest prompt (D-114)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_received_stores_pending_and_prompts():
    """Document without /ingest caption must store pending state and prompt."""
    import clive_telegram.bot as bot_module
    from clive_telegram.bot import handle_document_received

    update = _make_update(chat_id=99, has_document=True, filename="notes.txt")
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_document_received(update, context)

    # Pending state stored
    assert 99 in bot_module._pending_ingests
    pending = bot_module._pending_ingests[99]
    assert pending["original_filename"] == "notes.txt"
    assert pending["file_id"] == "tg_file_id_123"

    # Prompt sent to owner
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "notes.txt" in text
    assert "ingest_confirm" in text.lower()


@pytest.mark.asyncio
async def test_document_received_unauthenticated_ignored():
    """Unauthenticated document must be silently ignored."""
    import clive_telegram.bot as bot_module
    from clive_telegram.bot import handle_document_received

    update = _make_update(chat_id=99, has_document=True)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=False):
        await handle_document_received(update, context)

    assert 99 not in bot_module._pending_ingests
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_document_received_too_large_replies_error():
    """Document exceeding 10 MB limit must reply with size error (D-098)."""
    from clive_telegram.bot import handle_document_received

    oversized = 11 * 1024 * 1024  # 11 MB
    update = _make_update(chat_id=99, has_document=True, file_size=oversized)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_document_received(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "large" in text.lower() or "MB" in text


@pytest.mark.asyncio
async def test_document_received_overwrites_previous_pending():
    """Sending a second document before confirming must replace pending state."""
    import clive_telegram.bot as bot_module
    bot_module._pending_ingests[99] = {"original_filename": "old.pdf", "file_id": "old_id"}

    from clive_telegram.bot import handle_document_received
    update = _make_update(chat_id=99, has_document=True, filename="new.txt")
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_document_received(update, context)

    assert bot_module._pending_ingests[99]["original_filename"] == "new.txt"


# ---------------------------------------------------------------------------
# handle_ingest_confirm (D-114)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_confirm_no_pending_replies_guidance():
    """/ingest_confirm with no pending state must guide the user."""
    from clive_telegram.bot import handle_ingest_confirm

    update = _make_update(chat_id=99)
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_ingest_confirm(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "No pending" in text or "no pending" in text


@pytest.mark.asyncio
async def test_ingest_confirm_with_pending_uploads_and_emits():
    """/ingest_confirm with pending state must download, upload, emit ingest.received."""
    import clive_telegram.bot as bot_module
    bot_module._pending_ingests[99] = {
        "file_id": "tg_file_id_abc",
        "original_filename": "report.pdf",
        "file_size": 2048,
        "mime_type": "application/pdf",
    }

    from clive_telegram.bot import handle_ingest_confirm
    update = _make_update(chat_id=99)
    context = _make_context()

    # Mock Telegram file download
    fake_file = AsyncMock()
    fake_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake pdf content"))
    context.bot.get_file = AsyncMock(return_value=fake_file)

    emitted_events = []

    async def mock_emit(event_type, payload):
        emitted_events.append({"event_type": event_type, **payload})

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.sessions") as mock_sessions, \
         patch("clive_telegram.bot.upload_document", new_callable=AsyncMock) as mock_upload, \
         patch("clive_telegram.bot._emit_to_orchestrator", side_effect=mock_emit):
        mock_sessions.get_or_create.return_value = uuid.uuid4()
        mock_upload.return_value = None
        await handle_ingest_confirm(update, context)

    # Pending state cleared
    assert 99 not in bot_module._pending_ingests

    # Upload called
    mock_upload.assert_called_once()
    source_key_arg = mock_upload.call_args[0][0]
    assert "report.pdf" in source_key_arg

    # ingest.received emitted
    assert len(emitted_events) == 1
    assert emitted_events[0]["event_type"] == "ingest.received"
    payload = emitted_events[0]["payload"]
    assert payload["original_filename"] == "report.pdf"
    assert payload["chat_id"] == 99

    # Acknowledged
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "report.pdf" in text


@pytest.mark.asyncio
async def test_ingest_confirm_download_failure_replies_error():
    """/ingest_confirm must reply gracefully if Telegram download fails."""
    import clive_telegram.bot as bot_module
    bot_module._pending_ingests[99] = {
        "file_id": "bad_id",
        "original_filename": "broken.pdf",
        "file_size": 100,
        "mime_type": "application/pdf",
    }

    from clive_telegram.bot import handle_ingest_confirm
    update = _make_update(chat_id=99)
    context = _make_context()
    context.bot.get_file = AsyncMock(side_effect=RuntimeError("Telegram unavailable"))

    with patch("clive_telegram.bot.is_authenticated", return_value=True):
        await handle_ingest_confirm(update, context)

    # Pending state cleared even on failure
    assert 99 not in bot_module._pending_ingests

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "again" in text.lower() or "failed" in text.lower() or "retry" in text.lower()


# ---------------------------------------------------------------------------
# handle_list (v0.4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_with_documents_formats_reply():
    """/list with documents must return a formatted list."""
    from clive_telegram.bot import handle_list

    update = _make_update(chat_id=99)
    context = _make_context()

    mock_result = {
        "documents": [
            {"filename": "report.pdf", "source_key": "abc/report.pdf",
             "chunk_count": 42, "ingested_at": "2026-05-14T10:00:00"},
            {"filename": "notes.txt", "source_key": "def/notes.txt",
             "chunk_count": 8, "ingested_at": "2026-05-13T09:00:00"},
        ],
        "total": 2,
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_result)

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await handle_list(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "report.pdf" in text
    assert "notes.txt" in text
    assert "42" in text
    assert "2" in text  # total count


@pytest.mark.asyncio
async def test_list_empty_knowledge_base_replies_clearly():
    """/list with no documents must reply with a clear empty message."""
    from clive_telegram.bot import handle_list

    update = _make_update(chat_id=99)
    context = _make_context()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"documents": [], "total": 0})

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await handle_list(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "No" in text or "empty" in text.lower()


# ---------------------------------------------------------------------------
# handle_status (v0.4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_with_data_formats_reply():
    """/status with data must return formatted summary."""
    from clive_telegram.bot import handle_status

    update = _make_update(chat_id=99)
    context = _make_context()

    mock_result = {
        "doc_count": 5,
        "chunk_count": 237,
        "last_doc_name": "quarterly_report.pdf",
        "last_doc_at": "2026-05-14T10:30:00",
        "last_query_at": "2026-05-14T15:00:00",
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_result)

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await handle_status(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "5" in text  # doc count
    assert "237" in text or "237" in text.replace(",", "")  # chunk count
    assert "quarterly_report.pdf" in text


@pytest.mark.asyncio
async def test_status_empty_knowledge_base():
    """/status with no documents must reply gracefully."""
    from clive_telegram.bot import handle_status

    update = _make_update(chat_id=99)
    context = _make_context()

    mock_result = {
        "doc_count": 0,
        "chunk_count": 0,
        "last_doc_name": None,
        "last_doc_at": None,
        "last_query_at": None,
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_result)

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await handle_status(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    # Should mention empty/no documents and no query
    assert "empty" in text.lower() or "0" in text
    assert "none" in text.lower()
