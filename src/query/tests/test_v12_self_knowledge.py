"""Tests for Block 29 self-knowledge detection — v0.12 (D-149, D-150).

AC-1: documents queries short-circuit RAG and return document list.
AC-2: tools queries return live tool registry response.
AC-3: actions queries return action history.
AC-4: health queries return status summary.
AC-5: spend cap intent detected and routes as action.pending.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.handler import _detect_self_knowledge_intent, _detect_spend_cap_intent


# ── _detect_self_knowledge_intent ─────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "what documents do you know about",
    "what's in your knowledge base",
    "what is in your knowledge base",
    "list your documents",
    "what have you ingested",
    "What files do you have?",
])
def test_detect_sk_documents(text):
    assert _detect_self_knowledge_intent(text) == "documents"


@pytest.mark.parametrize("text", [
    "what tools do you have",
    "what can you do",
    "what are your capabilities",
    "what actions are available",
    "list your tools",
])
def test_detect_sk_tools(text):
    assert _detect_self_knowledge_intent(text) == "tools"


@pytest.mark.parametrize("text", [
    "what actions did you take",
    "what did you do",
    "recent actions",
    "action history",
    "what have you done this week",
])
def test_detect_sk_actions(text):
    assert _detect_self_knowledge_intent(text) == "actions"


@pytest.mark.parametrize("text", [
    "what workers do you have",
    "what background tasks",
    "what runs on a schedule",
    "list your workers",
])
def test_detect_sk_workers(text):
    assert _detect_self_knowledge_intent(text) == "workers"


@pytest.mark.parametrize("text", [
    "how much have you cost",
    "what's your status",
    "system health",
    "how much did you spend",
    "what's your daily cap",
    "system status",
])
def test_detect_sk_health(text):
    assert _detect_self_knowledge_intent(text) == "health"


@pytest.mark.parametrize("text", [
    "what is the capital of France",
    "summarise my notes on machine learning",
    "who wrote Hamlet",
    "remind me to call John",
    "search for recent AI papers",
])
def test_detect_sk_none_for_generic_queries(text):
    assert _detect_self_knowledge_intent(text) is None


# ── _detect_spend_cap_intent ──────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("set daily cap to $5", "5.0"),
    ("set my daily spend cap to $10.50", "10.5"),
    ("set daily limit to $3", "3.0"),
    ("set my budget to $0.50", "0.5"),
    ("set daily spend cap to 20", "20.0"),
])
def test_detect_spend_cap_matches(text, expected):
    result = _detect_spend_cap_intent(text)
    assert result == expected


@pytest.mark.parametrize("text", [
    "what's my daily cap",
    "system status",
    "remind me tomorrow",
    "set an alarm for 9am",
])
def test_detect_spend_cap_none_for_non_matching(text):
    assert _detect_spend_cap_intent(text) is None


# ── Self-knowledge path in handle_query ───────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_query_documents_returns_self_knowledge_response():
    """Document intent: query.response emitted with document list; vector RAG not called."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "what documents do you know about",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    async def fake_emit(event_type: str, payload: dict) -> None:  # NOSONAR
        emitted_events.append({"event_type": event_type, **payload})

    fake_docs_response = {
        "documents": [
            {"filename": "notes.pdf", "chunk_count": 12, "ingested_at": "2026-05-17T10:00:00"},
        ],
        "total": 1,
    }

    with (
        patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
        patch("query.handler._emit_event", side_effect=fake_emit),
        patch("query.handler.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_docs_response
        mock_resp.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from query.handler import handle_query
        await handle_query(event)

    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    text = response_events[0]["response_text"]
    assert "notes.pdf" in text
    assert "12" in text


@pytest.mark.asyncio
async def test_handle_query_spend_cap_emits_action_pending():
    """Spend cap intent: action.pending emitted with config.set_spend_cap type."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "set daily cap to $5",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    async def fake_emit(event_type: str, payload: dict) -> None:  # NOSONAR
        emitted_events.append({"event_type": event_type, **payload})

    with (
        patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
        patch("query.handler._emit_event", side_effect=fake_emit),
    ):
        from query.handler import handle_query
        await handle_query(event)

    pending_events = [e for e in emitted_events if e["event_type"] == "action.pending"]
    assert len(pending_events) == 1
    assert pending_events[0]["payload"]["action_type"] == "config.set_spend_cap"
    assert pending_events[0]["payload"]["action_target"] == "5.0"

    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    assert "$5.00" in response_events[0]["response_text"]
