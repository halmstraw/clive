"""Tests for orchestrator push.py — Block 13 outbound delivery functions."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent


def _make_event(event_type: str = "query.response", payload: dict | None = None) -> CLIVEEvent:
    return CLIVEEvent(
        event_type=event_type,
        source_block=8,
        payload=payload or {"response_text": "hello", "source_surface": "telegram"},
        conversation_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# push_query_to_block8
# ---------------------------------------------------------------------------

class TestPushQueryToBlock8:
    @pytest.mark.asyncio
    async def test_posts_to_query_service(self):
        from orchestrator.push import push_query_to_block8

        event = _make_event("query.received", {"input_text": "hi", "source_surface": "telegram"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("orchestrator.push.retrieval.get_conversation_history", AsyncMock(return_value=[])),
            patch("orchestrator.push.retrieval.store_conversation_turn", AsyncMock()),
            patch("orchestrator.push.httpx.AsyncClient", return_value=mock_client),
        ):
            await push_query_to_block8(event)

        mock_client.post.assert_called_once()
        call_url = mock_client.post.call_args[0][0]
        assert "/query" in call_url

    @pytest.mark.asyncio
    async def test_history_fetch_failure_is_non_fatal(self):
        from orchestrator.push import push_query_to_block8

        event = _make_event("query.received", {"input_text": "hi", "source_surface": "telegram"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("orchestrator.push.retrieval.get_conversation_history", AsyncMock(side_effect=Exception("db down"))),
            patch("orchestrator.push.retrieval.store_conversation_turn", AsyncMock()),
            patch("orchestrator.push.httpx.AsyncClient", return_value=mock_client),
        ):
            # Should not raise
            await push_query_to_block8(event)

        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_turn_failure_is_non_fatal(self):
        from orchestrator.push import push_query_to_block8

        event = _make_event("query.received", {"input_text": "hello", "source_surface": "telegram"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("orchestrator.push.retrieval.get_conversation_history", AsyncMock(return_value=[])),
            patch("orchestrator.push.retrieval.store_conversation_turn", AsyncMock(side_effect=Exception("write fail"))),
            patch("orchestrator.push.httpx.AsyncClient", return_value=mock_client),
        ):
            await push_query_to_block8(event)

        # Should succeed even if store fails


# ---------------------------------------------------------------------------
# push_response_to_surface
# ---------------------------------------------------------------------------

class TestPushResponseToSurface:
    @pytest.mark.asyncio
    async def test_routes_to_source_surface(self):
        from orchestrator.push import push_response_to_surface

        event = _make_event("query.response", {
            "response_text": "answer",
            "source_surface": "dashboard",
            "event_id": str(uuid.uuid4()),
        })

        mock_push = AsyncMock()
        with (
            patch("orchestrator.push.egress.push_to_surface", mock_push),
            patch("orchestrator.push.retrieval.store_conversation_turn", AsyncMock()),
        ):
            await push_response_to_surface(event)

        mock_push.assert_called_once()
        call_surface = mock_push.call_args[0][0]
        assert call_surface == "dashboard"

    @pytest.mark.asyncio
    async def test_defaults_to_telegram_surface(self):
        from orchestrator.push import push_response_to_surface

        event = _make_event("query.response", {"response_text": "answer"})

        mock_push = AsyncMock()
        with (
            patch("orchestrator.push.egress.push_to_surface", mock_push),
            patch("orchestrator.push.retrieval.store_conversation_turn", AsyncMock()),
        ):
            await push_response_to_surface(event)

        call_surface = mock_push.call_args[0][0]
        assert call_surface == "telegram"

    @pytest.mark.asyncio
    async def test_stores_assistant_turn(self):
        from orchestrator.push import push_response_to_surface

        event = _make_event("query.response", {"response_text": "my answer", "source_surface": "telegram"})

        mock_store = AsyncMock()
        with (
            patch("orchestrator.push.egress.push_to_surface", AsyncMock()),
            patch("orchestrator.push.retrieval.store_conversation_turn", mock_store),
        ):
            await push_response_to_surface(event)

        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args.kwargs
        assert call_kwargs.get("role") == "assistant" or mock_store.call_args[1].get("role") == "assistant"


# ---------------------------------------------------------------------------
# push_alert_to_surface
# ---------------------------------------------------------------------------

class TestPushAlertToSurface:
    @pytest.mark.asyncio
    async def test_broadcasts_to_all_surfaces(self):
        from orchestrator.push import push_alert_to_surface

        event = _make_event("alert.triggered", {"severity": "warn", "title": "alert", "body": "msg"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_alert_to_surface(event)

        mock_broadcast.assert_called_once_with("/alert", pytest.approx({"event_id": str(event.event_id), "severity": "warn", "title": "alert", "body": "msg"}, abs=1e-6))


# ---------------------------------------------------------------------------
# push_ingest_to_block15
# ---------------------------------------------------------------------------

class TestPushIngestToBlock15:
    @pytest.mark.asyncio
    async def test_posts_to_processing_service(self):
        from orchestrator.push import push_ingest_to_block15

        event = _make_event("ingest.received", {"filename": "doc.pdf"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("orchestrator.push.httpx.AsyncClient", return_value=mock_client):
            await push_ingest_to_block15(event)

        mock_client.post.assert_called_once()
        assert "/ingest" in mock_client.post.call_args[0][0]


# ---------------------------------------------------------------------------
# push_ingest_status_to_surface
# ---------------------------------------------------------------------------

class TestPushIngestStatus:
    @pytest.mark.asyncio
    async def test_sends_to_telegram_only(self):
        from orchestrator.push import push_ingest_status_to_surface

        event = _make_event("ingest.processed", {"filename": "doc.pdf", "status": "ok"})
        mock_surface = AsyncMock()
        with patch("orchestrator.push.egress.push_to_surface", mock_surface):
            await push_ingest_status_to_surface(event)

        mock_surface.assert_called_once()
        assert mock_surface.call_args[0][0] == "telegram"


# ---------------------------------------------------------------------------
# push_confirmation_to_surface
# ---------------------------------------------------------------------------

class TestPushConfirmationToSurface:
    @pytest.mark.asyncio
    async def test_broadcasts_confirmation(self):
        from orchestrator.push import push_confirmation_to_surface

        event = _make_event("action.confirmation_requested", {"action_type": "web.search"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_confirmation_to_surface(event)

        mock_broadcast.assert_called_once()
        assert mock_broadcast.call_args[0][0] == "/action-confirmation"


# ---------------------------------------------------------------------------
# push_action_outcome_to_surface
# ---------------------------------------------------------------------------

class TestPushActionOutcome:
    @pytest.mark.asyncio
    async def test_broadcasts_rejection(self):
        from orchestrator.push import push_action_outcome_to_surface

        event = _make_event("action.rejected", {"reason": "timeout"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_action_outcome_to_surface(event)

        mock_broadcast.assert_called_once()
        assert mock_broadcast.call_args[0][0] == "/action-outcome"


# ---------------------------------------------------------------------------
# push_confirmed_to_deletion
# ---------------------------------------------------------------------------

class TestPushConfirmedToDeletion:
    @pytest.mark.asyncio
    async def test_posts_to_processing_delete_endpoint(self):
        from orchestrator.push import push_confirmed_to_deletion

        event = _make_event("action.confirmed", {"action_type": "document.delete", "action_target": "doc.pdf"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("orchestrator.push.httpx.AsyncClient", return_value=mock_client):
            await push_confirmed_to_deletion(event)

        mock_client.post.assert_called_once()
        assert "/delete" in mock_client.post.call_args[0][0]


# ---------------------------------------------------------------------------
# push_deletion_result_to_surface
# ---------------------------------------------------------------------------

class TestPushDeletionResult:
    @pytest.mark.asyncio
    async def test_broadcasts_deletion_result(self):
        from orchestrator.push import push_deletion_result_to_surface

        event = _make_event("deletion.complete", {"filename": "doc.pdf"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_deletion_result_to_surface(event)

        mock_broadcast.assert_called_once()
        assert "/deletion-result" in mock_broadcast.call_args[0][0]


# ---------------------------------------------------------------------------
# push_cost_cap_notification_to_surface
# ---------------------------------------------------------------------------

class TestPushCostCapNotification:
    @pytest.mark.asyncio
    async def test_broadcasts_cap_alert_with_amounts(self):
        from orchestrator.push import push_cost_cap_notification_to_surface

        event = _make_event("cost.cap_exceeded", {"today_spend_usd": 5.5, "cap_usd": 5.0})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_cost_cap_notification_to_surface(event)

        mock_broadcast.assert_called_once()
        call_data = mock_broadcast.call_args[0][1]
        assert "5.0000" in call_data["body"]
        assert "5.5000" in call_data["body"]


# ---------------------------------------------------------------------------
# push_admin_tool_result_to_surface
# ---------------------------------------------------------------------------

class TestPushAdminToolResult:
    @pytest.mark.asyncio
    async def test_tool_updated_pushes_to_tool_updated_endpoint(self):
        from orchestrator.push import TOOL_UPDATED_ENDPOINT, push_admin_tool_result_to_surface

        event = _make_event("admin.tool_updated", {"tool_name": "web_search", "action": "disabled"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_admin_tool_result_to_surface(event)

        endpoint, call_data = mock_broadcast.call_args[0]
        assert endpoint == TOOL_UPDATED_ENDPOINT
        assert call_data["tool_name"] == "web_search"
        assert call_data["action"] == "disabled"

    @pytest.mark.asyncio
    async def test_tool_error_pushes_to_tool_error_endpoint(self):
        from orchestrator.push import TOOL_ERROR_ENDPOINT, push_admin_tool_result_to_surface

        event = _make_event("admin.tool_error", {"tool_name": "web_search", "reason": "not found"})
        mock_broadcast = AsyncMock()
        with patch("orchestrator.push.egress.push_to_all_surfaces", mock_broadcast):
            await push_admin_tool_result_to_surface(event)

        endpoint, call_data = mock_broadcast.call_args[0]
        assert endpoint == TOOL_ERROR_ENDPOINT
        assert call_data["tool_name"] == "web_search"
        assert call_data["reason"] == "not found"
