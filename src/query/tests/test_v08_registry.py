"""Tests for Block 8 Tool Registry integration — v0.8 (D-137, D-138).

Covers the three v0.8 acceptance criteria for Block 8:
  AC-registry-1: _find_tool_in_registry matches verbs to tools without
                 hardcoding tool names.
  AC-registry-2: When registry is empty, action intent responds with
                 "That capability is not currently available." and emits
                 no action event (D-138 mandatory test).
  AC-registry-3: When a matching tool exists, action.requested is emitted
                 with the correct tool_name.
  AC-registry-4: When no tool matches the verb, no action event is emitted
                 and the response contains "not currently available."
  AC-registry-5: Available tools appear in the LLM system prompt (name +
                 description only; permission_scope excluded).
  AC-registry-6: Empty registry produces a "no actions" statement in the
                 system prompt, not a blank or missing section.
  AC-registry-7: RegistryClient.refresh() fetches from DB and caches results.
  AC-registry-8: RegistryClient.refresh() on DB error: no exception raised,
                 stale/empty cache preserved, retry deferred by TTL.

All tests mock DB pool and LLM client. No live DB or LLM calls in CI (D-095).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.handler import _find_tool_in_registry
from query.registry import ToolDescriptor


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_tool(tool_name: str, display_name: str, description: str) -> ToolDescriptor:
    return ToolDescriptor(
        tool_name=tool_name,
        display_name=display_name,
        description=description,
        permission_scope=["read:test"],
    )


_REMINDER_TOOL = make_tool("reminder", "Reminder", "Sets time-based reminders that deliver via Telegram")
_WEB_SEARCH_TOOL = make_tool("web_search", "Web Search", "Searches the web via DuckDuckGo and returns summarised results")
_DELETE_TOOL = make_tool("delete_document", "Document Deletion", "Permanently removes a document from Block 16 storage")


# ── AC-registry-1: _find_tool_in_registry matching ───────────────────────────

def test_find_tool_matches_verb_as_prefix_of_tool_name_word():
    """'remind' is a prefix of 'reminder' — should match the reminder tool."""
    result = _find_tool_in_registry("remind", [_REMINDER_TOOL, _WEB_SEARCH_TOOL])
    assert result is not None
    assert result.tool_name == "reminder"


def test_find_tool_matches_verb_exactly_in_tool_name_words():
    """'search' exactly matches the 'search' word in 'web_search'."""
    result = _find_tool_in_registry("search", [_REMINDER_TOOL, _WEB_SEARCH_TOOL])
    assert result is not None
    assert result.tool_name == "web_search"


def test_find_tool_matches_delete_in_delete_document():
    """'delete' exactly matches the 'delete' word in 'delete_document'."""
    result = _find_tool_in_registry("delete", [_REMINDER_TOOL, _DELETE_TOOL])
    assert result is not None
    assert result.tool_name == "delete_document"


def test_find_tool_no_match_returns_none():
    """'email' does not match any word in reminder or web_search."""
    result = _find_tool_in_registry("email", [_REMINDER_TOOL, _WEB_SEARCH_TOOL])
    assert result is None


def test_find_tool_empty_registry_returns_none():
    """Empty tool list always returns None."""
    result = _find_tool_in_registry("remind", [])
    assert result is None


def test_find_tool_short_verb_excluded():
    """Verbs shorter than 3 characters return None to avoid false matches."""
    result = _find_tool_in_registry("do", [_REMINDER_TOOL, _WEB_SEARCH_TOOL])
    assert result is None


def test_find_tool_send_does_not_match_search_or_reminder():
    """'send' must not match 'web_search' or 'reminder' — no false positives."""
    result = _find_tool_in_registry("send", [_REMINDER_TOOL, _WEB_SEARCH_TOOL])
    assert result is None


# ── AC-registry-2: empty registry — mandatory D-138 test ─────────────────────

@pytest.mark.asyncio
async def test_empty_registry_action_intent_returns_not_available():
    """MANDATORY (D-138): empty registry → no action event emitted; response
    contains 'not currently available'."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "remind me to call John tomorrow",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    async def fake_emit(event_type: str, payload: dict) -> None:
        emitted_events.append({"event_type": event_type, **payload})

    with (
        patch("query.handler.registry.get_tools", AsyncMock(return_value=[])),
        patch("query.handler._emit_event", side_effect=fake_emit),
    ):
        from query.handler import handle_query
        await handle_query(event)

    # No action.requested event must be emitted (D-138)
    action_events = [e for e in emitted_events if e["event_type"] == "action.requested"]
    assert len(action_events) == 0, "action.requested must not be emitted for empty registry"

    # query.response must have been emitted with the correct message
    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    assert "not currently available" in response_events[0]["response_text"]


# ── AC-registry-3: matched tool emits action.requested ───────────────────────

@pytest.mark.asyncio
async def test_matched_tool_emits_action_requested_with_tool_name():
    """When a registry tool matches the action verb, action.requested is
    emitted with the correct tool_name and the query context."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "remind me to submit the report by Friday",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    async def fake_emit(event_type: str, payload: dict) -> None:
        emitted_events.append({"event_type": event_type, **payload})

    with (
        patch("query.handler.registry.get_tools", AsyncMock(return_value=[_REMINDER_TOOL])),
        patch("query.handler._emit_event", side_effect=fake_emit),
    ):
        from query.handler import handle_query
        await handle_query(event)

    # action.requested must be emitted
    action_events = [e for e in emitted_events if e["event_type"] == "action.requested"]
    assert len(action_events) == 1
    assert action_events[0]["tool_name"] == "reminder"
    assert action_events[0]["original_query_context"] == event["input_text"]

    # query.response must also be emitted (acknowledgment)
    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    # response should mention the tool display name
    assert "Reminder" in response_events[0]["response_text"]


# ── AC-registry-4: unmatched verb with non-empty registry ────────────────────

@pytest.mark.asyncio
async def test_unmatched_verb_with_registry_tools_returns_not_available():
    """'send' does not match reminder or web_search → no action event;
    response contains 'not currently available'."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "send an email to Alice",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    async def fake_emit(event_type: str, payload: dict) -> None:
        emitted_events.append({"event_type": event_type, **payload})

    tools = [_REMINDER_TOOL, _WEB_SEARCH_TOOL]

    with (
        patch("query.handler.registry.get_tools", AsyncMock(return_value=tools)),
        patch("query.handler._emit_event", side_effect=fake_emit),
    ):
        from query.handler import handle_query
        await handle_query(event)

    # No action.requested event
    action_events = [e for e in emitted_events if e["event_type"] == "action.requested"]
    assert len(action_events) == 0

    # Response: not currently available
    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    assert "not currently available" in response_events[0]["response_text"]


# ── AC-registry-5: tools injected in system prompt ───────────────────────────

@pytest.mark.asyncio
async def test_available_tools_appear_in_system_prompt():
    """When tools are available, the LLM system prompt includes tool_name and
    description. permission_scope must NOT be in the prompt."""
    from query.llm import complete

    tools = [
        ToolDescriptor("web_search", "Web Search", "Searches the web", ["read:web"]),
    ]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Here is what I found."
    mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

    with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)) as mock_llm:
        await complete(
            personality="You are CLIVE.",
            alignment_rules="No fabrication.",
            conversation_history=[],
            retrieved_chunks=[],
            user_query="What is the weather?",
            available_tools=tools,
        )

    call_kwargs = mock_llm.call_args.kwargs
    system_prompt = call_kwargs["system"]

    # Tool name and description must appear
    assert "web_search" in system_prompt
    assert "Searches the web" in system_prompt

    # permission_scope must NOT appear (D-138 constraint)
    assert "read:web" not in system_prompt


# ── AC-registry-6: empty registry produces "no actions" in system prompt ─────

@pytest.mark.asyncio
async def test_empty_tools_produces_no_actions_statement_in_system_prompt():
    """When the registry is empty, the system prompt states no actions are
    currently available (not a blank or missing section)."""
    from query.llm import complete

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Here is the answer."
    mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)

    with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)) as mock_llm:
        await complete(
            personality="You are CLIVE.",
            alignment_rules="No fabrication.",
            conversation_history=[],
            retrieved_chunks=[],
            user_query="What can you do?",
            available_tools=[],
        )

    call_kwargs = mock_llm.call_args.kwargs
    system_prompt = call_kwargs["system"]

    # Must explicitly state no actions available
    assert "no actions" in system_prompt.lower()


# ── AC-registry-7: RegistryClient fetches from DB ────────────────────────────

@pytest.mark.asyncio
async def test_registry_client_refresh_fetches_tools_from_db():
    """RegistryClient.refresh() queries the DB and populates the cache."""
    fake_rows = [
        {
            "tool_name": "web_search",
            "display_name": "Web Search",
            "description": "Searches the web",
            "permission_scope": ["read:web"],
        },
        {
            "tool_name": "reminder",
            "display_name": "Reminder",
            "description": "Sets reminders",
            "permission_scope": ["write:reminders"],
        },
    ]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fake_rows)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    from query.registry import RegistryClient
    client = RegistryClient()

    with patch("query.registry.get_pool", return_value=mock_pool):
        await client.refresh()
        tools = await client.get_tools()

    assert len(tools) == 2
    tool_names = {t.tool_name for t in tools}
    assert "web_search" in tool_names
    assert "reminder" in tool_names

    # permission_scope stored internally
    web_tool = next(t for t in tools if t.tool_name == "web_search")
    assert web_tool.permission_scope == ["read:web"]


# ── AC-registry-8: RegistryClient graceful DB error ──────────────────────────

@pytest.mark.asyncio
async def test_registry_client_db_error_returns_empty_cache_no_exception():
    """RegistryClient.refresh() on DB error: no exception raised, empty cache
    returned, retry deferred by TTL (timestamp updated even on failure)."""
    from query.registry import RegistryClient
    import time

    client = RegistryClient()

    with patch("query.registry.get_pool", side_effect=RuntimeError("pool not initialised")):
        # Must not raise
        await client.refresh()

    # Cache is empty (was never populated)
    tools = await client.get_tools()  # TTL not expired yet — returns stale []
    assert tools == []

    # Timestamp was updated — retry won't happen immediately on next get_tools()
    # (i.e., _cache_ts > 0 means the TTL clock is running)
    assert client._cache_ts > 0, "_cache_ts must be updated even on DB failure"
