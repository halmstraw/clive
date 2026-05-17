"""Tests for search_handler.py and reminder_handler.py."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent


def _search_event(payload: dict | None = None) -> CLIVEEvent:
    return CLIVEEvent(
        event_type="action.confirmed",
        source_block=9,
        payload=payload or {
            "action_type": "web.search",
            "action_target": "python asyncio",
            "chat_id": 12345,
        },
        conversation_id=uuid.uuid4(),
    )


def _reminder_event(payload: dict | None = None) -> CLIVEEvent:
    return CLIVEEvent(
        event_type="action.confirmed",
        source_block=9,
        payload=payload or {
            "action_type": "reminder.schedule",
            "chat_id": 12345,
            "reminder_message": "Call dentist",
            "fire_at": "2026-05-20T09:00:00",
        },
        conversation_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# search_handler.py
# ---------------------------------------------------------------------------

class TestSearchHandlerHandleConfirmed:
    @pytest.mark.asyncio
    async def test_brave_search_success(self):
        from orchestrator import search_handler

        brave_response = {
            "web": {
                "results": [
                    {"title": "Title 1", "description": "Snippet 1", "url": "https://example.com/1"},
                    {"title": "Title 2", "description": "Snippet 2", "url": "https://example.com/2"},
                ]
            }
        }

        mock_search_resp = MagicMock()
        mock_search_resp.raise_for_status = MagicMock()
        mock_search_resp.json = MagicMock(return_value=brave_response)

        mock_push_resp = MagicMock()
        mock_push_resp.raise_for_status = MagicMock()

        call_count = 0

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        async def side_effect_get(url, **kwargs):
            return mock_search_resp

        async def side_effect_post(url, **kwargs):
            return mock_push_resp

        mock_client.get = AsyncMock(side_effect=side_effect_get)
        mock_client.post = AsyncMock(side_effect=side_effect_post)

        event = _search_event()

        with (
            patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"SEARCH_API_KEY": "test-key", "SEARCH_API_PROVIDER": "brave"}),
        ):
            await search_handler.handle_confirmed(event)

        mock_client.get.assert_called_once()
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_serpapi_search_success(self):
        from orchestrator import search_handler

        serpapi_response = {
            "organic_results": [
                {"title": "Result", "snippet": "snippet", "link": "https://example.com"},
            ]
        }

        mock_search_resp = MagicMock()
        mock_search_resp.raise_for_status = MagicMock()
        mock_search_resp.json = MagicMock(return_value=serpapi_response)

        mock_push_resp = MagicMock()
        mock_push_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_search_resp)
        mock_client.post = AsyncMock(return_value=mock_push_resp)

        event = _search_event()

        with (
            patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"SEARCH_API_KEY": "test-key", "SEARCH_API_PROVIDER": "serpapi"}),
        ):
            await search_handler.handle_confirmed(event)

        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_query_pushes_error(self):
        from orchestrator import search_handler

        event = _search_event({"action_type": "web.search", "chat_id": 123, "action_target": ""})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"SEARCH_API_KEY": "key"}),
        ):
            await search_handler.handle_confirmed(event)

        # Should call /alert for error
        mock_client.post.assert_called_once()
        assert "/alert" in mock_client.post.call_args[0][0]

    @pytest.mark.asyncio
    async def test_missing_api_key_pushes_error(self):
        from orchestrator import search_handler

        event = _search_event()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        import os
        os.environ.pop("SEARCH_API_KEY", None)

        with patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client):
            await search_handler.handle_confirmed(event)

        assert "/alert" in mock_client.post.call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_results_sends_empty_message(self):
        from orchestrator import search_handler

        empty_response = {"web": {"results": []}}

        mock_search_resp = MagicMock()
        mock_search_resp.raise_for_status = MagicMock()
        mock_search_resp.json = MagicMock(return_value=empty_response)

        mock_push_resp = MagicMock()
        mock_push_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_search_resp)
        mock_client.post = AsyncMock(return_value=mock_push_resp)

        with (
            patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"SEARCH_API_KEY": "key", "SEARCH_API_PROVIDER": "brave"}),
        ):
            await search_handler.handle_confirmed(event=_search_event())

        push_payload = mock_client.post.call_args[1]["json"]
        assert "No results found" in push_payload["response_text"]

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        from orchestrator.search_handler import _call_provider

        with pytest.raises(ValueError, match="Unknown SEARCH_API_PROVIDER"):
            await _call_provider("unknown_provider", "query", "key")

    @pytest.mark.asyncio
    async def test_search_api_failure_pushes_error(self):
        from orchestrator import search_handler

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

        mock_push_resp = MagicMock()
        mock_push_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_push_resp)

        with (
            patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"SEARCH_API_KEY": "key", "SEARCH_API_PROVIDER": "brave"}),
        ):
            await search_handler.handle_confirmed(event=_search_event())

        # Should have called /alert error push
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_error_handles_http_failure(self):
        from orchestrator.search_handler import _push_error

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with patch("orchestrator.search_handler.httpx.AsyncClient", return_value=mock_client):
            # Should not raise
            await _push_error("test error message")


# ---------------------------------------------------------------------------
# reminder_handler.py
# ---------------------------------------------------------------------------

class TestReminderHandlerHandleConfirmed:
    @pytest.mark.asyncio
    async def test_stores_reminder_in_db(self):
        from orchestrator import reminder_handler

        event = _reminder_event()

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        original_pool = reminder_handler._pool
        try:
            reminder_handler._pool = mock_pool
            with patch("orchestrator.reminder_handler.httpx.AsyncClient", return_value=mock_client):
                await reminder_handler.handle_confirmed(event)
            mock_conn.execute.assert_called_once()
        finally:
            reminder_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_missing_message_pushes_error(self):
        from orchestrator import reminder_handler

        event = _reminder_event({"action_type": "reminder.schedule", "chat_id": 123, "reminder_message": "", "fire_at": "2026-05-20T09:00:00"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        original_pool = reminder_handler._pool
        try:
            reminder_handler._pool = MagicMock()
            with patch("orchestrator.reminder_handler.httpx.AsyncClient", return_value=mock_client):
                await reminder_handler.handle_confirmed(event)
            # Should call /alert
            assert "/alert" in mock_client.post.call_args[0][0]
        finally:
            reminder_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_invalid_fire_at_pushes_error(self):
        from orchestrator import reminder_handler

        event = _reminder_event({
            "action_type": "reminder.schedule",
            "chat_id": 123,
            "reminder_message": "Call dentist",
            "fire_at": "not-a-date",
        })

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        original_pool = reminder_handler._pool
        try:
            reminder_handler._pool = MagicMock()
            with patch("orchestrator.reminder_handler.httpx.AsyncClient", return_value=mock_client):
                await reminder_handler.handle_confirmed(event)
            assert "/alert" in mock_client.post.call_args[0][0]
        finally:
            reminder_handler._pool = original_pool

    def test_get_pool_raises_when_not_init(self):
        from orchestrator import reminder_handler

        original = reminder_handler._pool
        try:
            reminder_handler._pool = None
            with pytest.raises(RuntimeError):
                reminder_handler._get_pool()
        finally:
            reminder_handler._pool = original


class TestFireDueReminders:
    @pytest.mark.asyncio
    async def test_fires_due_reminders(self):
        from orchestrator import reminder_handler

        rid = uuid.uuid4()
        mock_rows = [{"reminder_id": rid, "chat_id": 12345, "message": "Call dentist"}]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        original_pool = reminder_handler._pool
        try:
            reminder_handler._pool = mock_pool
            with patch("orchestrator.reminder_handler.httpx.AsyncClient", return_value=mock_client):
                await reminder_handler._fire_due_reminders("http://telegram:8082")
            mock_client.post.assert_called_once()
            push_json = mock_client.post.call_args[1]["json"]
            assert "Call dentist" in push_json["response_text"]
        finally:
            reminder_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_push_failure_logged_not_raised(self):
        from orchestrator import reminder_handler

        rid = uuid.uuid4()
        mock_rows = [{"reminder_id": rid, "chat_id": 12345, "message": "Test"}]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network fail"))

        original_pool = reminder_handler._pool
        try:
            reminder_handler._pool = mock_pool
            with patch("orchestrator.reminder_handler.httpx.AsyncClient", return_value=mock_client):
                # Should not raise
                await reminder_handler._fire_due_reminders("http://telegram:8082")
        finally:
            reminder_handler._pool = original_pool


# ---------------------------------------------------------------------------
# main.py — dispatch_action_confirmed routing
# ---------------------------------------------------------------------------

class TestDispatchActionConfirmed:
    @pytest.mark.asyncio
    async def test_routes_document_delete(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "document.delete", "action_target": "doc.pdf"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.push_confirmed_to_deletion", mock_fn):
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_routes_web_search(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "web.search", "action_target": "test"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.search_handler") as mock_sh:
            mock_sh.handle_confirmed = mock_fn
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_routes_reminder_schedule(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "reminder.schedule", "action_target": "test"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.reminder_handler") as mock_rh:
            mock_rh.handle_confirmed = mock_fn
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_routes_knowledge_prune(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "knowledge.prune"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.knowledge_maintenance") as mock_km:
            mock_km.handle_prune_confirmed = mock_fn
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_routes_config_set_spend_cap(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "config.set_spend_cap", "action_target": "5.0"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.config_handler") as mock_ch:
            mock_ch.handle_config_set_spend_cap = mock_fn
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_routes_worker_reschedule(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "worker.reschedule", "action_target": "daily_digest:0 10 * * *"},
        )

        mock_fn = AsyncMock()
        with patch("orchestrator.main.config_handler") as mock_ch:
            mock_ch.handle_worker_reschedule = mock_fn
            await dispatch_action_confirmed(event)

        mock_fn.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_unknown_action_type_logs_warning(self):
        from orchestrator.main import dispatch_action_confirmed

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "totally.unknown"},
        )

        # Should not raise
        await dispatch_action_confirmed(event)
