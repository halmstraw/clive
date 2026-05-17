"""Tests for telegram main.py HTTP handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


async def _make_app() -> web.Application:
    """Build the Telegram HTTP push receiver app for testing."""
    from clive_telegram.main import (
        handle_response_push,
        handle_alert_push,
        handle_ingest_status_push,
        handle_action_confirmation_push,
        handle_action_outcome_push,
        handle_deletion_result_push,
        handle_tool_updated_push,
        handle_tool_error_push,
        handle_health,
        handle_metrics,
    )

    app = web.Application()
    app.router.add_post("/response", handle_response_push)
    app.router.add_post("/alert", handle_alert_push)
    app.router.add_post("/ingest-status", handle_ingest_status_push)
    app.router.add_post("/action-confirmation", handle_action_confirmation_push)
    app.router.add_post("/action-outcome", handle_action_outcome_push)
    app.router.add_post("/deletion-result", handle_deletion_result_push)
    app.router.add_post("/tool-updated", handle_tool_updated_push)
    app.router.add_post("/tool-error", handle_tool_error_push)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    return app


MOCK_OWNER_CHAT_ID = 12345


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_returns_ok(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert data["block"] == 23


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

class TestHandleMetrics:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /response
# ---------------------------------------------------------------------------

class TestHandleResponsePush:
    @pytest.mark.asyncio
    async def test_accepts_and_returns_accepted(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_response", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/response", json={
                    "event_id": "evt-001",
                    "response_text": "hello",
                    "confidence": {"threshold_met": True},
                })
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "accepted"


# ---------------------------------------------------------------------------
# POST /alert
# ---------------------------------------------------------------------------

class TestHandleAlertPush:
    @pytest.mark.asyncio
    async def test_accepts_alert(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_alert", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/alert", json={
                    "severity": "warn",
                    "title": "Disk space",
                    "body": "Low disk",
                })
                assert resp.status == 200
                assert (await resp.json())["status"] == "accepted"


# ---------------------------------------------------------------------------
# POST /ingest-status
# ---------------------------------------------------------------------------

class TestHandleIngestStatusPush:
    @pytest.mark.asyncio
    async def test_accepts_ingest_status(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_ingest_status", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/ingest-status", json={
                    "event_type": "ingest.processed",
                    "filename": "doc.pdf",
                    "payload": {"status": "ok"},
                })
                assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /action-confirmation
# ---------------------------------------------------------------------------

class TestHandleActionConfirmationPush:
    @pytest.mark.asyncio
    async def test_accepts_with_chat_id(self):
        app = await _make_app()
        with patch("clive_telegram.main.deliver_action_confirmation", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/action-confirmation", json={
                    "action_request_id": "req-001",
                    "chat_id": MOCK_OWNER_CHAT_ID,
                    "action_type": "web.search",
                })
                assert resp.status == 200

    @pytest.mark.asyncio
    async def test_accepts_with_payload_chat_id(self):
        """chat_id in nested payload is also used."""
        app = await _make_app()
        with patch("clive_telegram.main.deliver_action_confirmation", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/action-confirmation", json={
                    "action_request_id": "req-001",
                    "payload": {"chat_id": MOCK_OWNER_CHAT_ID},
                })
                assert resp.status == 200

    @pytest.mark.asyncio
    async def test_falls_back_to_owner_chat_id_when_no_chat_id(self):
        """Falls back to get_owner_chat_id() when chat_id is missing."""
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_action_confirmation", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/action-confirmation", json={
                    "action_request_id": "req-001",
                })
                assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /action-outcome
# ---------------------------------------------------------------------------

class TestHandleActionOutcomePush:
    @pytest.mark.asyncio
    async def test_accepts_action_outcome(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_action_outcome", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/action-outcome", json={
                    "event_type": "action.rejected",
                    "reason": "timeout",
                })
                assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /deletion-result
# ---------------------------------------------------------------------------

class TestHandleDeletionResultPush:
    @pytest.mark.asyncio
    async def test_accepts_deletion_result(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_deletion_result", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/deletion-result", json={
                    "event_type": "deletion.complete",
                    "filename": "doc.pdf",
                })
                assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /tool-updated
# ---------------------------------------------------------------------------

class TestHandleToolUpdatedPush:
    @pytest.mark.asyncio
    async def test_accepts_tool_updated(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_tool_updated", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/tool-updated", json={
                    "tool_name": "web_search",
                    "action": "disabled",
                })
                assert resp.status == 200


# ---------------------------------------------------------------------------
# POST /tool-error
# ---------------------------------------------------------------------------

class TestHandleToolErrorPush:
    @pytest.mark.asyncio
    async def test_accepts_tool_error(self):
        app = await _make_app()
        with (
            patch("clive_telegram.main.get_owner_chat_id", return_value=MOCK_OWNER_CHAT_ID),
            patch("clive_telegram.main.deliver_tool_error", AsyncMock()),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/tool-error", json={
                    "tool_name": "web_search",
                    "reason": "not found",
                })
                assert resp.status == 200
