"""Tests for dashboard api.py and push.py."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_app() -> web.Application:
    from clive_dashboard.api import (
        handle_query,
        handle_poll_response,
        handle_history,
        handle_pending,
        handle_confirm,
        handle_cancel,
    )
    from clive_dashboard.push import (
        handle_response_push,
        handle_confirmation_push,
        handle_alert_push,
        handle_action_outcome_push,
        handle_deletion_result_push,
    )

    app = web.Application()
    app.router.add_post("/api/query", handle_query)
    app.router.add_get("/api/response", handle_poll_response)
    app.router.add_post("/api/history", handle_history)
    app.router.add_get("/api/pending", handle_pending)
    app.router.add_post("/api/confirm/{action_request_id}", handle_confirm)
    app.router.add_post("/api/cancel/{action_request_id}", handle_cancel)
    # Push endpoints
    app.router.add_post("/push/response", handle_response_push)
    app.router.add_post("/push/action-confirmation", handle_confirmation_push)
    app.router.add_post("/push/alert", handle_alert_push)
    app.router.add_post("/push/action-outcome", handle_action_outcome_push)
    app.router.add_post("/push/deletion-result", handle_deletion_result_push)
    return app


def _mock_session(user_id: str = "owner") -> dict:
    return {"user_id": user_id, "session_token": "test-token"}


# ---------------------------------------------------------------------------
# api.py — set_pending_response (unit test)
# ---------------------------------------------------------------------------

class TestSetPendingResponse:
    def test_stores_response_by_conversation_id(self):
        from clive_dashboard.api import set_pending_response, _pending_responses

        cid = str(uuid.uuid4())
        set_pending_response(cid, {"response_text": "hello"})
        assert cid in _pending_responses
        assert _pending_responses[cid]["response_text"] == "hello"
        # Clean up
        _pending_responses.pop(cid, None)


# ---------------------------------------------------------------------------
# api.py — POST /api/query
# ---------------------------------------------------------------------------

class TestHandleQuery:
    @pytest.mark.asyncio
    async def test_submits_query_and_returns_ids(self):
        app = await _make_app()

        session = _mock_session()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/query", json={"input_text": "hello"})
                assert resp.status == 200
                data = await resp.json()
                assert "conversation_id" in data
                assert "event_id" in data
                assert data["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_returns_400_for_missing_input_text(self):
        app = await _make_app()
        session = _mock_session()

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/query", json={})
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()
        session = _mock_session()

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(
                    "/api/query",
                    data="not-json",
                    headers={"Content-Type": "application/json"},
                )
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_502_on_orchestrator_failure(self):
        app = await _make_app()
        session = _mock_session()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/query", json={"input_text": "hello"})
                assert resp.status == 502

    @pytest.mark.asyncio
    async def test_uses_provided_conversation_id(self):
        app = await _make_app()
        session = _mock_session()
        cid = str(uuid.uuid4())

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/query", json={"input_text": "hello", "conversation_id": cid})
                data = await resp.json()
                assert data["conversation_id"] == cid


# ---------------------------------------------------------------------------
# api.py — GET /api/response
# ---------------------------------------------------------------------------

class TestHandlePollResponse:
    @pytest.mark.asyncio
    async def test_returns_202_when_pending(self):
        app = await _make_app()
        session = _mock_session()

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get(f"/api/response?conversation_id={uuid.uuid4()}")
                assert resp.status == 202

    @pytest.mark.asyncio
    async def test_returns_400_without_conversation_id(self):
        app = await _make_app()
        session = _mock_session()

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/api/response")
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_ready_with_response_when_available(self):
        from clive_dashboard.api import set_pending_response, _pending_responses
        app = await _make_app()
        session = _mock_session()

        cid = str(uuid.uuid4())
        set_pending_response(cid, {"response_text": "the answer", "event_id": "evt-001"})

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get(f"/api/response?conversation_id={cid}")
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ready"
                assert data["response_text"] == "the answer"


# ---------------------------------------------------------------------------
# api.py — POST /api/history
# ---------------------------------------------------------------------------

class TestHandleHistory:
    @pytest.mark.asyncio
    async def test_returns_turns(self):
        app = await _make_app()
        session = _mock_session()
        cid = str(uuid.uuid4())

        mock_result = {"turns": [{"role": "user", "content": "hi"}], "conversation_id": cid}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/history", json={"conversation_id": cid})
                assert resp.status == 200
                data = await resp.json()
                assert len(data["turns"]) == 1

    @pytest.mark.asyncio
    async def test_returns_400_without_conversation_id(self):
        app = await _make_app()
        session = _mock_session()

        with patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/history", json={})
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_502_on_orchestrator_failure(self):
        app = await _make_app()
        session = _mock_session()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("error"))

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/history", json={"conversation_id": str(uuid.uuid4())})
                assert resp.status == 502


# ---------------------------------------------------------------------------
# api.py — GET /api/pending
# ---------------------------------------------------------------------------

class TestHandlePending:
    @pytest.mark.asyncio
    async def test_returns_pending_actions(self):
        app = await _make_app()
        session = _mock_session()

        mock_result = {"actions": [{"action_type": "web.search"}], "count": 1}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/api/pending")
                assert resp.status == 200
                data = await resp.json()
                assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_returns_502_on_orchestrator_failure(self):
        app = await _make_app()
        session = _mock_session()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("error"))

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/api/pending")
                assert resp.status == 502


# ---------------------------------------------------------------------------
# api.py — POST /api/confirm/<id>
# ---------------------------------------------------------------------------

class TestHandleConfirm:
    @pytest.mark.asyncio
    async def test_emits_confirmed_owner_response(self):
        app = await _make_app()
        session = _mock_session()
        rid = str(uuid.uuid4())

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(f"/api/confirm/{rid}")
                assert resp.status == 200
                data = await resp.json()
                assert data["decision"] == "confirmed"

        post_json = mock_client.post.call_args[1]["json"]
        assert post_json["payload"]["decision"] == "confirmed"
        assert post_json["payload"]["action_request_id"] == rid

    @pytest.mark.asyncio
    async def test_returns_502_on_failure(self):
        app = await _make_app()
        session = _mock_session()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("error"))

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(f"/api/confirm/{uuid.uuid4()}")
                assert resp.status == 502


# ---------------------------------------------------------------------------
# api.py — POST /api/cancel/<id>
# ---------------------------------------------------------------------------

class TestHandleCancel:
    @pytest.mark.asyncio
    async def test_emits_rejected_owner_response(self):
        app = await _make_app()
        session = _mock_session()
        rid = str(uuid.uuid4())

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(f"/api/cancel/{rid}")
                assert resp.status == 200
                data = await resp.json()
                assert data["decision"] == "rejected"

    @pytest.mark.asyncio
    async def test_returns_502_on_failure(self):
        app = await _make_app()
        session = _mock_session()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("error"))

        with (
            patch("clive_dashboard.api.require_session", AsyncMock(return_value=session)),
            patch("clive_dashboard.api.httpx.AsyncClient", return_value=mock_client),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(f"/api/cancel/{uuid.uuid4()}")
                assert resp.status == 502


# ---------------------------------------------------------------------------
# push.py — handle_response_push
# ---------------------------------------------------------------------------

class TestHandleResponsePush:
    @pytest.mark.asyncio
    async def test_stores_response_and_returns_accepted(self):
        app = await _make_app()
        cid = str(uuid.uuid4())

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/response", json={
                "conversation_id": cid,
                "event_id": "evt-001",
                "response_text": "hello",
            })
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_accepts_push_with_no_conversation_id(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/response", json={"event_id": "evt-001", "response_text": "hi"})
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/push/response",
                data="not-json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# push.py — handle_confirmation_push
# ---------------------------------------------------------------------------

class TestHandleConfirmationPush:
    @pytest.mark.asyncio
    async def test_stores_confirmation(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/action-confirmation", json={
                "action_request_id": str(uuid.uuid4()),
                "event_id": "evt-001",
                "action_type": "web.search",
            })
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/push/action-confirmation",
                data="bad",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# push.py — handle_alert_push
# ---------------------------------------------------------------------------

class TestHandleAlertPush:
    @pytest.mark.asyncio
    async def test_accepts_alert(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/alert", json={
                "severity": "warn",
                "title": "Disk space low",
                "body": "Disk 90% full",
            })
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/push/alert",
                data="bad",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# push.py — handle_action_outcome_push
# ---------------------------------------------------------------------------

class TestHandleActionOutcomePush:
    @pytest.mark.asyncio
    async def test_accepts_outcome(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/action-outcome", json={
                "event_id": "evt-001",
                "event_type": "action.rejected",
                "action_request_id": str(uuid.uuid4()),
            })
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/push/action-outcome",
                data="bad",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# push.py — handle_deletion_result_push
# ---------------------------------------------------------------------------

class TestHandleDeletionResultPush:
    @pytest.mark.asyncio
    async def test_accepts_deletion_result(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/push/deletion-result", json={
                "event_id": "evt-001",
                "event_type": "deletion.complete",
                "filename": "doc.pdf",
            })
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/push/deletion-result",
                data="bad",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
