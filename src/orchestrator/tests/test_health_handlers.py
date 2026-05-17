"""Tests for orchestrator health.py HTTP handlers."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


async def _make_app() -> web.Application:
    """Build the orchestrator aiohttp app for testing."""
    from orchestrator.health import (
        handle_alerts,
        handle_event_intake,
        handle_health,
        handle_metrics,
        handle_retrieve_action_history,
        handle_retrieve_conversation_history,
        handle_retrieve_document_by_filename,
        handle_retrieve_document_list,
        handle_retrieve_knowledge,
        handle_retrieve_pending_actions,
        handle_retrieve_status,
        handle_retrieve_system_document,
        handle_retrieve_workers,
    )

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_post("/events", handle_event_intake)
    app.router.add_post("/alerts", handle_alerts)
    app.router.add_post("/retrieve/knowledge", handle_retrieve_knowledge)
    app.router.add_post("/retrieve/system-document", handle_retrieve_system_document)
    app.router.add_post("/retrieve/document-by-filename", handle_retrieve_document_by_filename)
    app.router.add_post("/retrieve/document-list", handle_retrieve_document_list)
    app.router.add_post("/retrieve/status", handle_retrieve_status)
    app.router.add_post("/retrieve/conversation-history", handle_retrieve_conversation_history)
    app.router.add_post("/retrieve/pending-actions", handle_retrieve_pending_actions)
    app.router.add_post("/retrieve/action-history", handle_retrieve_action_history)
    app.router.add_post("/retrieve/workers", handle_retrieve_workers)
    return app


# ---------------------------------------------------------------------------
# /health
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
            assert data["block"] == 13


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

class TestHandleMetrics:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200


# ---------------------------------------------------------------------------
# /events (event intake)
# ---------------------------------------------------------------------------

class TestHandleEventIntake:
    @pytest.mark.asyncio
    async def test_accepts_valid_event(self):
        app = await _make_app()
        with patch("orchestrator.health.bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            async with TestClient(TestServer(app)) as client:
                payload = {
                    "event_type": "query.received",
                    "source_block": 23,
                    "payload": {"input_text": "hello"},
                }
                resp = await client.post("/events", json=payload)
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "accepted"


# ---------------------------------------------------------------------------
# /alerts
# ---------------------------------------------------------------------------

class TestHandleAlerts:
    @pytest.mark.asyncio
    async def test_accepts_valid_grafana_payload(self):
        app = await _make_app()
        with patch("orchestrator.health.bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            async with TestClient(TestServer(app)) as client:
                payload = {
                    "alerts": [
                        {
                            "labels": {"alertname": "DiskFull", "severity": "critical"},
                            "annotations": {"summary": "Disk is full", "description": "90% used"},
                            "status": "firing",
                            "startsAt": "2026-05-17T12:00:00Z",
                            "fingerprint": "abc123",
                        }
                    ]
                }
                resp = await client.post("/alerts", json=payload)
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "accepted"
                mock_bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_400_for_missing_alerts_field(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/alerts", json={"title": "test"})
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_400_for_alerts_not_list(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/alerts", json={"alerts": "not a list"})
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_json(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/alerts",
                data="not-json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_empty_alerts_list_accepted(self):
        app = await _make_app()
        with patch("orchestrator.health.bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/alerts", json={"alerts": []})
                assert resp.status == 200
                mock_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# /retrieve/knowledge
# ---------------------------------------------------------------------------

class TestHandleRetrieveKnowledge:
    @pytest.mark.asyncio
    async def test_returns_result_from_retrieval(self):
        app = await _make_app()
        mock_result = {"ranked_chunks": [{"content": "chunk text", "relevance_score": 0.9}]}
        with patch("orchestrator.health.retrieve", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/knowledge", json={
                    "retrieval_query": "test query",
                    "zone_scope": "personal",
                })
                assert resp.status == 200
                data = await resp.json()
                assert "ranked_chunks" in data


# ---------------------------------------------------------------------------
# /retrieve/system-document
# ---------------------------------------------------------------------------

class TestHandleRetrieveSystemDocument:
    @pytest.mark.asyncio
    async def test_returns_system_document(self):
        app = await _make_app()
        mock_result = {"document_content": "You are CLIVE."}
        with patch("orchestrator.health.retrieve_system_document", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/system-document", json={
                    "document_type": "personality",
                    "zone_scope": "personal",
                })
                assert resp.status == 200
                data = await resp.json()
                assert "document_content" in data


# ---------------------------------------------------------------------------
# /retrieve/document-by-filename
# ---------------------------------------------------------------------------

class TestHandleRetrieveDocumentByFilename:
    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        app = await _make_app()
        with patch("orchestrator.health.retrieve_document_by_filename", AsyncMock(return_value={"source_keys": []})):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/document-by-filename", json={
                    "filename": "missing.pdf",
                    "zone_scope": "personal",
                })
                assert resp.status == 404

    @pytest.mark.asyncio
    async def test_returns_400_when_filename_missing(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/retrieve/document-by-filename", json={"zone_scope": "personal"})
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_source_keys_when_found(self):
        app = await _make_app()
        mock_result = {"source_keys": ["raw/doc.pdf"], "chunk_count": 5}
        with patch("orchestrator.health.retrieve_document_by_filename", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/document-by-filename", json={
                    "filename": "doc.pdf",
                    "zone_scope": "personal",
                })
                assert resp.status == 200
                data = await resp.json()
                assert data["chunk_count"] == 5


# ---------------------------------------------------------------------------
# /retrieve/document-list
# ---------------------------------------------------------------------------

class TestHandleRetrieveDocumentList:
    @pytest.mark.asyncio
    async def test_returns_document_list(self):
        app = await _make_app()
        mock_result = {"documents": [{"filename": "a.pdf"}], "total": 1}
        with patch("orchestrator.health.retrieve_document_list", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/document-list", json={"zone_scope": "personal"})
                assert resp.status == 200
                data = await resp.json()
                assert data["total"] == 1


# ---------------------------------------------------------------------------
# /retrieve/status
# ---------------------------------------------------------------------------

class TestHandleRetrieveStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self):
        app = await _make_app()
        mock_result = {"doc_count": 5, "chunk_count": 100}
        with patch("orchestrator.health.retrieve_status", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/status", json={"zone_scope": "personal"})
                assert resp.status == 200
                data = await resp.json()
                assert data["doc_count"] == 5


# ---------------------------------------------------------------------------
# /retrieve/conversation-history
# ---------------------------------------------------------------------------

class TestHandleRetrieveConversationHistory:
    @pytest.mark.asyncio
    async def test_returns_turns(self):
        app = await _make_app()
        cid = str(uuid.uuid4())
        mock_turns = [{"role": "user", "content": "hi"}]
        with patch("orchestrator.health.get_conversation_history", AsyncMock(return_value=mock_turns)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/conversation-history", json={"conversation_id": cid})
                assert resp.status == 200
                data = await resp.json()
                assert data["conversation_id"] == cid
                assert len(data["turns"]) == 1

    @pytest.mark.asyncio
    async def test_returns_400_when_no_conversation_id(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/retrieve/conversation-history", json={})
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_uuid(self):
        app = await _make_app()
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/retrieve/conversation-history", json={"conversation_id": "not-a-uuid"})
            assert resp.status == 400


# ---------------------------------------------------------------------------
# /retrieve/pending-actions
# ---------------------------------------------------------------------------

class TestHandleRetrievePendingActions:
    @pytest.mark.asyncio
    async def test_returns_pending_actions(self):
        app = await _make_app()
        mock_actions = [{"action_type": "web.search", "status": "pending"}]
        with patch("orchestrator.health.get_pending_actions", AsyncMock(return_value=mock_actions)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/pending-actions", json={"zone_scope": "personal"})
                assert resp.status == 200
                data = await resp.json()
                assert data["count"] == 1


# ---------------------------------------------------------------------------
# /retrieve/action-history
# ---------------------------------------------------------------------------

class TestHandleRetrieveActionHistory:
    @pytest.mark.asyncio
    async def test_returns_action_history(self):
        app = await _make_app()
        mock_result = {"actions": [], "total": 0, "days": 7}
        with patch("orchestrator.health.retrieve_action_history", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/action-history", json={"zone_scope": "personal", "days": 7})
                assert resp.status == 200
                data = await resp.json()
                assert data["total"] == 0


# ---------------------------------------------------------------------------
# /retrieve/workers
# ---------------------------------------------------------------------------

class TestHandleRetrieveWorkers:
    @pytest.mark.asyncio
    async def test_returns_workers(self):
        app = await _make_app()
        mock_result = {"workers": [{"worker_name": "daily_digest"}], "total": 1}
        with patch("orchestrator.health.retrieve_workers", AsyncMock(return_value=mock_result)):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/retrieve/workers", json={})
                assert resp.status == 200
                data = await resp.json()
                assert data["total"] == 1
