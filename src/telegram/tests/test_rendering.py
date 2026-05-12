"""Rendering edge-case tests — D-094, D-095.

Verifies that ingest status messages are delivered as plain text and never
with parse_mode=Markdown.  Document filenames containing underscores would
cause Telegram to return BadRequest if parse_mode=Markdown were used (D-094).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_bot_app():
    mock_app = MagicMock()
    mock_send = AsyncMock()
    mock_app.bot.send_message = mock_send

    import clive_telegram.bot as bot_module
    original = bot_module._app
    bot_module._app = mock_app
    yield mock_app, mock_send
    bot_module._app = original


@pytest.mark.asyncio
async def test_processed_status_no_parse_mode(mock_bot_app):
    """ingest.processed messages must not use parse_mode (D-094)."""
    from clive_telegram.bot import deliver_ingest_status

    _, mock_send = mock_bot_app
    payload = {
        "event_type": "ingest.processed",
        "source_key": "abc123/my_document_with_underscores.pdf",
        "chunk_count": 7,
        "inserted_count": 7,
    }
    await deliver_ingest_status(payload, chat_id=99)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert "parse_mode" not in kwargs, (
        "deliver_ingest_status must not pass parse_mode — filenames with underscores "
        "break Telegram Markdown rendering (D-094)"
    )


@pytest.mark.asyncio
async def test_rejected_status_no_parse_mode(mock_bot_app):
    """ingest.rejected messages must not use parse_mode (D-094)."""
    from clive_telegram.bot import deliver_ingest_status

    _, mock_send = mock_bot_app
    payload = {
        "event_type": "ingest.rejected",
        "source_key": "abc123/report_q1_final_v2.pdf",
        "reason": "extraction_failed",
    }
    await deliver_ingest_status(payload, chat_id=99)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert "parse_mode" not in kwargs


@pytest.mark.asyncio
async def test_processed_status_contains_chunk_count(mock_bot_app):
    """Processed follow-up message includes the chunk count."""
    from clive_telegram.bot import deliver_ingest_status

    _, mock_send = mock_bot_app
    payload = {
        "event_type": "ingest.processed",
        "source_key": "uuid/report.pdf",
        "chunk_count": 12,
        "inserted_count": 12,
    }
    await deliver_ingest_status(payload, chat_id=99)

    text = mock_send.call_args.kwargs.get("text", "")
    assert "12" in text, f"Chunk count not in delivery text: {text!r}"


@pytest.mark.asyncio
async def test_unknown_event_type_sends_nothing(mock_bot_app):
    """Unknown event types must not send any message."""
    from clive_telegram.bot import deliver_ingest_status

    _, mock_send = mock_bot_app
    await deliver_ingest_status({"event_type": "some.unknown.event"}, chat_id=99)
    mock_send.assert_not_called()
