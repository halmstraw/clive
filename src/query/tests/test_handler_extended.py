"""Extended tests for query handler — covering uncovered code paths."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.handler import (
    _detect_self_knowledge_intent,
    _detect_spend_cap_intent,
    _find_tool_in_registry,
)
from query.registry import ToolDescriptor


# ---------------------------------------------------------------------------
# _detect_self_knowledge_intent
# ---------------------------------------------------------------------------

class TestDetectSelfKnowledgeIntent:
    def test_documents_intent(self):
        assert _detect_self_knowledge_intent("what documents do you know about") == "documents"

    def test_tools_intent(self):
        assert _detect_self_knowledge_intent("what can you do") == "tools"

    def test_actions_intent(self):
        assert _detect_self_knowledge_intent("recent actions") == "actions"

    def test_workers_intent(self):
        assert _detect_self_knowledge_intent("what background tasks do you run") == "workers"

    def test_health_intent(self):
        assert _detect_self_knowledge_intent("how much have you cost") == "health"

    def test_status_intent(self):
        assert _detect_self_knowledge_intent("what's your status") == "health"

    def test_no_match_returns_none(self):
        assert _detect_self_knowledge_intent("What is the capital of France?") is None

    def test_case_insensitive(self):
        assert _detect_self_knowledge_intent("WHAT CAN YOU DO") == "tools"

    def test_documents_variant(self):
        assert _detect_self_knowledge_intent("list your documents") == "documents"

    def test_list_tools(self):
        assert _detect_self_knowledge_intent("list your tools") == "tools"


# ---------------------------------------------------------------------------
# _detect_spend_cap_intent
# ---------------------------------------------------------------------------

class TestDetectSpendCapIntent:
    def test_detects_set_cap_with_dollar(self):
        result = _detect_spend_cap_intent("set my daily spend cap to $5.00")
        assert result == "5.0"

    def test_detects_set_cap_without_dollar(self):
        # Regex: set + optional(my) + optional(daily) + optional(spend) + cap/limit/budget + to + amount
        result = _detect_spend_cap_intent("set my cap to 10")
        assert result == "10.0"

    def test_detects_budget_word(self):
        result = _detect_spend_cap_intent("set my budget to $3.50")
        assert result == "3.5"

    def test_detects_limit_word(self):
        result = _detect_spend_cap_intent("set my daily limit to 7")
        assert result == "7.0"

    def test_no_match_returns_none(self):
        assert _detect_spend_cap_intent("what is the cap") is None

    def test_no_match_plain_question(self):
        assert _detect_spend_cap_intent("how much did I spend today") is None


# ---------------------------------------------------------------------------
# _find_tool_in_registry
# ---------------------------------------------------------------------------

class TestFindToolInRegistry:
    def _make_tools(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(tool_name="web_search", display_name="Web Search", description="Search the web"),
            ToolDescriptor(tool_name="reminder_schedule", display_name="Reminder Schedule", description="Schedule reminders"),
        ]

    def test_finds_by_exact_word_in_name(self):
        tools = self._make_tools()
        result = _find_tool_in_registry("search", tools)
        assert result is not None
        assert result.tool_name == "web_search"

    def test_finds_by_prefix(self):
        tools = self._make_tools()
        result = _find_tool_in_registry("remind", tools)
        assert result is not None
        assert result.tool_name == "reminder_schedule"

    def test_returns_none_for_no_match(self):
        tools = self._make_tools()
        result = _find_tool_in_registry("email", tools)
        assert result is None

    def test_returns_none_for_empty_registry(self):
        result = _find_tool_in_registry("search", [])
        assert result is None

    def test_short_verb_returns_none(self):
        tools = self._make_tools()
        # "go" is < 3 chars
        result = _find_tool_in_registry("go", tools)
        assert result is None

    def test_exact_match_by_display_name(self):
        tools = [ToolDescriptor(tool_name="my_tool", display_name="delete document", description="Deletes a document")]
        result = _find_tool_in_registry("delete", tools)
        assert result is not None


# ---------------------------------------------------------------------------
# handle_query — self-knowledge intent path
# ---------------------------------------------------------------------------

class TestHandleQuerySelfKnowledge:
    def _base_event(self, text: str) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": text,
            "zone_scope": "personal",
            "conversation_history": [],
        }

    @pytest.mark.asyncio
    async def test_self_knowledge_documents_short_circuits_rag(self):
        from query.handler import handle_query

        event = self._base_event("list your documents")
        emitted: list[dict] = []

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"documents": [{"filename": "a.pdf", "chunk_count": 3, "ingested_at": "2026-05-01T00:00:00"}]})

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

        response_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(response_events) == 1
        assert "a.pdf" in response_events[0].get("response_text", "")

    @pytest.mark.asyncio
    async def test_self_knowledge_tools_intent(self):
        from query.handler import handle_query

        event = self._base_event("what tools do you have")
        emitted: list[dict] = []

        tool = ToolDescriptor(tool_name="web_search", display_name="Web Search", description="Search the web")

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[tool])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
        ):
            await handle_query(event)

        response_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(response_events) == 1
        assert "Web Search" in response_events[0].get("response_text", "")

    @pytest.mark.asyncio
    async def test_self_knowledge_tools_no_tools(self):
        from query.handler import handle_query

        event = self._base_event("what tools do you have")
        emitted: list[dict] = []

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
        ):
            await handle_query(event)

        response_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert "No tools" in response_events[0].get("response_text", "")


# ---------------------------------------------------------------------------
# handle_query — spend cap config intent
# ---------------------------------------------------------------------------

class TestHandleQuerySpendCapIntent:
    @pytest.mark.asyncio
    async def test_spend_cap_intent_emits_action_pending(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "set my daily spend cap to $5.00",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
        ):
            await handle_query(event)

        # Should emit action.pending for config.set_spend_cap
        action_events = [e for e in emitted if e.get("event_type") == "action.pending"]
        assert len(action_events) == 1
        assert action_events[0]["payload"]["action_type"] == "config.set_spend_cap"
        assert action_events[0]["payload"]["action_target"] == "5.0"

        # Should also emit query.response confirming
        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(resp_events) == 1
        assert "5.00" in resp_events[0]["response_text"]


# ---------------------------------------------------------------------------
# handle_query — action intent with tool in registry
# ---------------------------------------------------------------------------

class TestHandleQueryActionIntent:
    @pytest.mark.asyncio
    async def test_action_with_matching_tool_emits_action_requested(self):
        from query.handler import handle_query

        # "remind" is in ACTION_VERBS; "reminder_schedule" tool matches via prefix
        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "remind me to check the report at 9am",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        tool = ToolDescriptor(
            tool_name="reminder_schedule",
            display_name="Reminder Schedule",
            description="Schedule reminders",
        )

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[tool])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
        ):
            await handle_query(event)

        action_events = [e for e in emitted if e.get("event_type") == "action.requested"]
        assert len(action_events) == 1
        assert action_events[0]["tool_name"] == "reminder_schedule"

    @pytest.mark.asyncio
    async def test_action_without_matching_tool_returns_not_available(self):
        from query.handler import handle_query

        event = {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "input_text": "send an email to Alice",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        with (
            patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
            patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))),
        ):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(resp_events) == 1
        assert "not currently available" in resp_events[0]["response_text"]


# ---------------------------------------------------------------------------
# handle_query — idempotency cache hit
# ---------------------------------------------------------------------------

class TestHandleQueryIdempotency:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_response(self):
        from query.handler import handle_query
        from query.idempotency import cache

        conversation_id = uuid.uuid4()
        event_id = uuid.uuid4()
        cached_payload = {
            "event_id": str(event_id),
            "response_text": "cached answer",
            "confidence": {"threshold_met": True},
            "chunk_ids": [],
            "source_surface": "telegram",
        }
        cache.set(conversation_id, event_id, cached_payload)

        event = {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "input_text": "any query",
            "zone_scope": "personal",
            "conversation_history": [],
        }
        emitted: list[dict] = []

        with patch("query.handler._emit_event", AsyncMock(side_effect=lambda t, p: emitted.append({"event_type": t, **p}))):
            await handle_query(event)

        resp_events = [e for e in emitted if e.get("event_type") == "query.response"]
        assert len(resp_events) == 1
        assert resp_events[0]["response_text"] == "cached answer"


# ---------------------------------------------------------------------------
# _update_chunk_retrieval_stats
# ---------------------------------------------------------------------------

class TestUpdateChunkRetrievalStats:
    @pytest.mark.asyncio
    async def test_skips_on_empty_chunk_ids(self):
        from query.handler import _update_chunk_retrieval_stats

        with patch("query.handler.get_pool") as mock_pool:
            await _update_chunk_retrieval_stats([])
            mock_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_chunks_in_db(self):
        from query.handler import _update_chunk_retrieval_stats

        # The handler calls pool.execute() directly (not pool.acquire())
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock()

        with patch("query.handler.get_pool", return_value=mock_pool):
            await _update_chunk_retrieval_stats([str(uuid.uuid4()), str(uuid.uuid4())])

        mock_pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_failure_is_non_fatal(self):
        from query.handler import _update_chunk_retrieval_stats

        with patch("query.handler.get_pool", side_effect=RuntimeError("pool not ready")):
            # Should not raise
            await _update_chunk_retrieval_stats([str(uuid.uuid4())])
