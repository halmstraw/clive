"""v0.7 Block 9 — Unit tests for search_handler and reminder_handler.

Criteria covered:
  Criterion 3: search handler calls API and delivers result to Block 23
  Criterion 3: search handler handles API failure gracefully
  Criterion 5: reminder handler stores confirmed reminder to DB
  Criterion 5: reminder polling fires due reminders and marks them fired
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent
from orchestrator.search_handler import (
    _brave_search,
    _serpapi_search,
    handle_confirmed as search_handle_confirmed,
)
from orchestrator.reminder_handler import (
    _fire_due_reminders,
    handle_confirmed as reminder_handle_confirmed,
    reminder_poll,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(action_type: str, **payload_extra) -> CLIVEEvent:
    return CLIVEEvent(
        event_type="action.confirmed",
        source_block=9,
        conversation_id=uuid.uuid4(),
        payload={
            "action_type": action_type,
            "chat_id": 12345,
            **payload_extra,
        },
    )


# ---------------------------------------------------------------------------
# search_handler tests
# ---------------------------------------------------------------------------

class TestSearchHandlerConfirmed:
    @pytest.mark.asyncio
    async def test_search_delivers_results_to_surface(self):
        event = _make_event("web.search", action_target="Python asyncio tutorial")

        brave_results = [
            {"title": "Asyncio Guide", "snippet": "Learn asyncio.", "url": "https://example.com/1"},
            {"title": "Python Docs", "snippet": "Official docs.", "url": "https://example.com/2"},
        ]

        with (
            patch("orchestrator.search_handler.os.environ.get", side_effect=lambda k, d="": {
                "SEARCH_API_KEY": "test-key",
                "SEARCH_API_PROVIDER": "brave",
                "TELEGRAM_SERVICE_URL": "http://telegram:8082",
            }.get(k, d)),
            patch("orchestrator.search_handler._brave_search", new_callable=AsyncMock, return_value=brave_results),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())

            await search_handle_confirmed(event)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs["json"] if call_kwargs.kwargs else call_kwargs[1]["json"]
        assert "Python asyncio tutorial" in body["response_text"]
        assert "Asyncio Guide" in body["response_text"]

    @pytest.mark.asyncio
    async def test_search_missing_query_sends_error(self):
        event = _make_event("web.search", action_target="")

        with (
            patch("orchestrator.search_handler.os.environ.get", side_effect=lambda k, d="": {
                "SEARCH_API_KEY": "test-key",
                "TELEGRAM_SERVICE_URL": "http://telegram:8082",
            }.get(k, d)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await search_handle_confirmed(event)

        # Should push to /alert, not /response
        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert "/alert" in url

    @pytest.mark.asyncio
    async def test_search_no_api_key_sends_error(self):
        event = _make_event("web.search", action_target="something")

        with (
            patch("orchestrator.search_handler.os.environ.get", return_value=""),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await search_handle_confirmed(event)

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert "/alert" in url

    @pytest.mark.asyncio
    async def test_search_api_failure_sends_error(self):
        event = _make_event("web.search", action_target="test query")

        with (
            patch("orchestrator.search_handler.os.environ.get", side_effect=lambda k, d="": {
                "SEARCH_API_KEY": "test-key",
                "SEARCH_API_PROVIDER": "brave",
                "TELEGRAM_SERVICE_URL": "http://telegram:8082",
            }.get(k, d)),
            patch(
                "orchestrator.search_handler._brave_search",
                new_callable=AsyncMock,
                side_effect=Exception("connection refused"),
            ),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await search_handle_confirmed(event)

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert "/alert" in url

    @pytest.mark.asyncio
    async def test_brave_search_parses_response(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"title": "T1", "description": "S1", "url": "https://u1.com"},
                    {"title": "T2", "description": "S2", "url": "https://u2.com"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            results = await _brave_search("test", "key")

        assert len(results) == 2
        assert results[0]["title"] == "T1"
        assert results[0]["url"] == "https://u1.com"

    @pytest.mark.asyncio
    async def test_serpapi_search_parses_response(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic_results": [
                {"title": "T1", "snippet": "S1", "link": "https://u1.com"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            results = await _serpapi_search("test", "key")

        assert len(results) == 1
        assert results[0]["title"] == "T1"


# ---------------------------------------------------------------------------
# reminder_handler tests
# ---------------------------------------------------------------------------

class TestReminderHandlerConfirmed:
    @pytest.mark.asyncio
    async def test_reminder_stored_in_db(self):
        fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
        event = _make_event(
            "reminder.schedule",
            reminder_message="Call dentist",
            fire_at=fire_at.isoformat(),
        )

        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with (
            patch("orchestrator.reminder_handler._pool", mock_pool),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await reminder_handle_confirmed(event)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        sql = call_args.args[0]
        assert "scheduled_reminders" in sql
        assert "pending" in sql

    @pytest.mark.asyncio
    async def test_reminder_missing_message_sends_error(self):
        fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
        event = _make_event("reminder.schedule", reminder_message="", fire_at=fire_at.isoformat())

        with (
            patch("orchestrator.reminder_handler._pool", MagicMock()),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await reminder_handle_confirmed(event)

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert "/alert" in url

    @pytest.mark.asyncio
    async def test_reminder_invalid_fire_at_sends_error(self):
        event = _make_event("reminder.schedule", reminder_message="Buy milk", fire_at="not-a-date")

        with (
            patch("orchestrator.reminder_handler._pool", MagicMock()),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await reminder_handle_confirmed(event)

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert "/alert" in url


class TestReminderPoll:
    @pytest.mark.asyncio
    async def test_poll_fires_due_reminder(self):
        reminder_id = uuid.uuid4()
        due_row = {"reminder_id": reminder_id, "chat_id": 12345, "message": "Call dentist"}

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [due_row]
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        push_calls = []

        def mock_post(url, **kwargs):
            push_calls.append(url)
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with (
            patch("orchestrator.reminder_handler._pool", mock_pool),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = mock_post

            await _fire_due_reminders("http://telegram:8082")

        # At least one push to /response was made
        assert any("/response" in url for url in push_calls)

    @pytest.mark.asyncio
    async def test_poll_marks_reminder_fired(self):
        """The UPDATE...RETURNING fires atomically — verify SQL contains status = 'fired'."""
        reminder_id = uuid.uuid4()
        due_row = {"reminder_id": reminder_id, "chat_id": 12345, "message": "Check email"}

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [due_row]
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with (
            patch("orchestrator.reminder_handler._pool", mock_pool),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

            await _fire_due_reminders("http://telegram:8082")

        # The UPDATE SQL should reference status = 'fired'
        fetch_sql = mock_conn.fetch.call_args.args[0]
        assert "fired" in fetch_sql

    @pytest.mark.asyncio
    async def test_poll_no_due_reminders_does_nothing(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with (
            patch("orchestrator.reminder_handler._pool", mock_pool),
            patch("orchestrator.reminder_handler.asyncio.sleep", new_callable=AsyncMock),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import asyncio
            task = asyncio.create_task(reminder_poll())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        mock_client.post.assert_not_called()
