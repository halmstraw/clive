"""Tests for query/handler.py — _handle_self_knowledge_query all intents."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.registry import ToolDescriptor


def _make_orchestrator_response(body: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=body)
    return mock_resp


async def _run_self_knowledge(text: str) -> list[dict]:
    """Helper: run handle_query with text and return emitted events."""
    from query.handler import handle_query

    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": text,
        "zone_scope": "personal",
        "conversation_history": [],
    }
    emitted: list[dict] = []

    with patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))):
        with patch("query.handler.registry.get_tools", AsyncMock(return_value=[])):
            yield event, emitted
            await handle_query(event)


class TestHandleSelfKnowledgeQueryActions:
    @pytest.mark.asyncio
    async def test_actions_intent_with_recent_actions(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "what actions did you take",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        actions_response = {
            "actions": [
                {
                    "action_type": "web.search",
                    "action_target": "python",
                    "status": "confirmed",
                    "executed_at": "2026-05-17T10:00:00",
                }
            ]
        }

        mock_resp = _make_orchestrator_response(actions_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(resp_events) == 1
        text = resp_events[0]["response_text"]
        assert "web.search" in text

    @pytest.mark.asyncio
    async def test_actions_intent_no_actions(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "recent actions",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        mock_resp = _make_orchestrator_response({"actions": []})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert "No actions" in resp_events[0]["response_text"]


class TestHandleSelfKnowledgeQueryWorkers:
    @pytest.mark.asyncio
    async def test_workers_intent_with_workers(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "what background tasks",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        workers_response = {
            "workers": [
                {
                    "worker_name": "daily_digest",
                    "display_name": "Daily Digest",
                    "description": "Daily summary",
                    "schedule": "0 8 * * *",
                    "enabled": True,
                }
            ]
        }

        mock_resp = _make_orchestrator_response(workers_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert "Daily Digest" in resp_events[0]["response_text"]

    @pytest.mark.asyncio
    async def test_workers_intent_no_workers(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "list your workers",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        mock_resp = _make_orchestrator_response({"workers": []})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert "No workers" in resp_events[0]["response_text"]


class TestHandleSelfKnowledgeQueryHealth:
    @pytest.mark.asyncio
    async def test_health_intent_returns_status(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "system status",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        health_response = {
            "doc_count": 5,
            "chunk_count": 100,
            "llm_spend_today_usd": 0.0431,
            "daily_cap_usd": 10.0,
            "last_query_at": "2026-05-17T10:00:00",
            "last_doc_name": "report.pdf",
            "last_doc_at": "2026-05-16T08:00:00",
        }

        mock_resp = _make_orchestrator_response(health_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        text = resp_events[0]["response_text"]
        assert "Documents" in text
        assert "5" in text


class TestHandleSelfKnowledgeQueryDocumentsNoData:
    @pytest.mark.asyncio
    async def test_empty_knowledge_base(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "what documents do you know about",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        mock_resp = _make_orchestrator_response({"documents": []})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert "empty" in resp_events[0]["response_text"].lower()


class TestHandleSelfKnowledgeQueryFailure:
    @pytest.mark.asyncio
    async def test_http_failure_returns_graceful_fallback(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "what workers do you have",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
            patch("query.handler.httpx.AsyncClient", return_value=mock_client),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(resp_events) == 1
        assert "Could not retrieve" in resp_events[0]["response_text"]
