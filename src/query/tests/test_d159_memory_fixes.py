"""Tests for D-159 memory entity bug fixes.

Covers three behavioral changes:
  Fix 1 — Entity storage occurs BEFORE query.response is emitted.
  Fix 2 — embed_batch is called with "key: value" strings, not bare values.
  Fix 3 — store_entities SQL uses ON CONFLICT (entity_type, key) DO UPDATE.

All tests mock DB pool, LLM client, and HTTP calls. No live dependencies.
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resp(data: dict) -> MagicMock:
    """Return a mock httpx response that raises_for_status and returns data."""
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=data)
    return r


def _make_http_client_class() -> MagicMock:
    """Return a mock that stands in for httpx.AsyncClient (the class).

    When code does ``async with httpx.AsyncClient() as client:``, this mock
    is called (returning the instance mock), and the instance mock is entered
    as an async context manager.

    Two-level mock structure:
      - httpx.AsyncClient      → class_mock  (MagicMock)
      - httpx.AsyncClient()    → instance    (AsyncMock, async ctx manager)
      - instance.post(...)     → per-URL responses
    """
    call_count = [0]

    async def fake_post(url, **_kwargs):
        if "system-document" in url:
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_resp({"document_content": "You are CLIVE."})
            return _make_resp({"document_content": "No fabrication."})
        return _make_resp({"ranked_chunks": []})

    instance = AsyncMock()
    instance.post = AsyncMock(side_effect=fake_post)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    # class_mock() returns instance — simulates AsyncClient(...)
    class_mock = MagicMock(return_value=instance)
    return class_mock


def _make_event(input_text: str = "My favourite colour is red") -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": input_text,
        "zone_scope": "personal",
        "source_surface": "telegram",
        "conversation_history": [],
    }


def _build_patches(
    http_client_class: MagicMock,
    extract_entities_mock: AsyncMock,
    embed_batch_mock: AsyncMock,
    store_entities_mock: AsyncMock,
    emit_event_mock: AsyncMock,
) -> list[tuple[str, object]]:
    """Return the standard patch list for handle_query integration tests.

    Patches query.handler.httpx.AsyncClient (the class as seen by handler.py)
    so that async-with usage works correctly in the patched context.
    """
    return [
        ("query.handler.cache.get", MagicMock(return_value=None)),
        ("query.handler.registry.get_tools", AsyncMock(return_value=[])),
        ("query.handler.get_daily_cap", AsyncMock(return_value=None)),
        ("query.handler.llm.embed", AsyncMock(return_value=[0.1] * 1536)),
        ("query.handler.memory.retrieve_entities", AsyncMock(return_value=[])),
        ("query.handler.llm.complete", AsyncMock(return_value=(
            "Got it, I'll remember that.",
            {"model": "test-model", "prompt_tokens": 10, "completion_tokens": 5},
        ))),
        ("query.handler.compute_cost", MagicMock(return_value=0.001)),
        ("query.handler.record_usage", AsyncMock(return_value=None)),
        ("query.handler.llm.extract_entities", extract_entities_mock),
        ("query.handler.llm.embed_batch", embed_batch_mock),
        ("query.handler.memory.store_entities", store_entities_mock),
        ("query.handler.memory.consolidate_if_needed", AsyncMock(return_value=None)),
        ("query.handler.cache.set", MagicMock(return_value=None)),
        ("query.handler._emit_event", emit_event_mock),
        ("query.handler._update_chunk_retrieval_stats", AsyncMock(return_value=None)),
        ("query.handler.llm_tokens_total", MagicMock()),
        ("query.handler.llm_cost_usd_total", MagicMock()),
        ("query.handler.queries_total", MagicMock()),
        ("query.handler.query_duration_seconds", MagicMock()),
        ("query.handler.retrieval_chunks_returned_total", MagicMock()),
        # Patch the class as seen from the handler module namespace
        ("query.handler.httpx.AsyncClient", http_client_class),
    ]


# ---------------------------------------------------------------------------
# Fix 3 — store_entities uses upsert SQL (ON CONFLICT)
# ---------------------------------------------------------------------------

class TestStoreEntitiesUpsert:
    """Verify store_entities SQL contains ON CONFLICT upsert clause (D-159 Fix 3)."""

    @pytest.mark.asyncio
    async def test_upsert_sql_contains_on_conflict(self):
        """store_entities SQL must include ON CONFLICT (entity_type, key) DO UPDATE."""
        from query.memory import store_entities

        entities = [{"entity_type": "preference", "key": "favourite_colour", "value": "red"}]
        embeddings = [[0.1] * 1536]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.memory.get_pool", return_value=mock_pool):
            await store_entities(entities, source_turn_id=None, embeddings=embeddings)

        mock_conn.execute.assert_called_once()
        sql_executed = mock_conn.execute.call_args[0][0]

        assert "ON CONFLICT" in sql_executed
        assert "entity_type, key" in sql_executed
        assert "DO UPDATE" in sql_executed

    @pytest.mark.asyncio
    async def test_upsert_sets_value_and_embedding_from_excluded(self):
        """The DO UPDATE clause must set value and embedding from EXCLUDED."""
        from query.memory import store_entities

        entities = [{"entity_type": "preference", "key": "favourite_colour", "value": "blue"}]
        embeddings = [[0.2] * 1536]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.memory.get_pool", return_value=mock_pool):
            await store_entities(entities, source_turn_id=None, embeddings=embeddings)

        sql_executed = mock_conn.execute.call_args[0][0]
        assert "EXCLUDED.value" in sql_executed
        assert "EXCLUDED.embedding" in sql_executed

    @pytest.mark.asyncio
    async def test_upsert_called_once_per_entity(self):
        """One execute call per entity — each entity is upserted independently."""
        from query.memory import store_entities

        entities = [
            {"entity_type": "preference", "key": "favourite_colour", "value": "red"},
            {"entity_type": "preference", "key": "favourite_food", "value": "pizza"},
        ]
        embeddings = [[0.1] * 1536, [0.2] * 1536]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        with patch("query.memory.get_pool", return_value=mock_pool):
            await store_entities(entities, source_turn_id=None, embeddings=embeddings)

        assert mock_conn.execute.call_count == 2


# ---------------------------------------------------------------------------
# Fix 2 — embed_batch uses "key: value" strings, not bare values
# ---------------------------------------------------------------------------

class TestEmbeddingKeyValueFormat:
    """Verify embed_batch receives "key: value" format (D-159 Fix 2)."""

    @pytest.mark.asyncio
    async def test_embed_batch_receives_key_value_strings(self):
        """When entities are extracted, embed_batch is called with 'key: value' strings."""
        from query.handler import handle_query

        embed_batch_mock = AsyncMock(return_value=[[0.5] * 1536])
        extract_entities_mock = AsyncMock(return_value=[
            {"entity_type": "preference", "key": "favourite_colour", "value": "red"}
        ])
        emit_mock = AsyncMock(return_value=None)
        store_mock = AsyncMock(return_value=None)

        patches = _build_patches(
            http_client_class=_make_http_client_class(),
            extract_entities_mock=extract_entities_mock,
            embed_batch_mock=embed_batch_mock,
            store_entities_mock=store_mock,
            emit_event_mock=emit_mock,
        )

        with ExitStack() as stack:
            for target, new_val in patches:
                stack.enter_context(patch(target, new_val))
            await handle_query(_make_event())

        embed_batch_mock.assert_called_once()
        strings_passed = embed_batch_mock.call_args[0][0]
        assert strings_passed == ["favourite_colour: red"], (
            f"Expected ['favourite_colour: red'], got {strings_passed!r}"
        )

    @pytest.mark.asyncio
    async def test_bare_value_not_used(self):
        """embed_batch must NOT be called with bare value ('red') without the key."""
        from query.handler import handle_query

        embed_batch_mock = AsyncMock(return_value=[[0.5] * 1536])
        extract_entities_mock = AsyncMock(return_value=[
            {"entity_type": "preference", "key": "favourite_colour", "value": "red"}
        ])
        emit_mock = AsyncMock(return_value=None)
        store_mock = AsyncMock(return_value=None)

        patches = _build_patches(
            http_client_class=_make_http_client_class(),
            extract_entities_mock=extract_entities_mock,
            embed_batch_mock=embed_batch_mock,
            store_entities_mock=store_mock,
            emit_event_mock=emit_mock,
        )

        with ExitStack() as stack:
            for target, new_val in patches:
                stack.enter_context(patch(target, new_val))
            await handle_query(_make_event())

        strings_passed = embed_batch_mock.call_args[0][0]
        assert strings_passed != ["red"], "embed_batch must not receive bare value without key"


# ---------------------------------------------------------------------------
# Fix 1 — entity storage occurs BEFORE query.response is emitted
# ---------------------------------------------------------------------------

class TestEntityStorageBeforeResponse:
    """Verify store_entities is called before _emit_event(query.response) — D-159 Fix 1."""

    @pytest.mark.asyncio
    async def test_store_entities_called_before_query_response_emit(self):
        """Call order: store_entities must precede _emit_event with query.response."""
        from query.handler import handle_query

        call_order: list[str] = []

        async def tracking_store(*_args, **_kwargs):
            call_order.append("store_entities")

        async def tracking_emit(event_type, _payload):
            if event_type == "query.response":
                call_order.append("emit_query_response")

        patches = _build_patches(
            http_client_class=_make_http_client_class(),
            extract_entities_mock=AsyncMock(return_value=[
                {"entity_type": "preference", "key": "favourite_colour", "value": "red"}
            ]),
            embed_batch_mock=AsyncMock(return_value=[[0.5] * 1536]),
            store_entities_mock=AsyncMock(side_effect=tracking_store),
            emit_event_mock=AsyncMock(side_effect=tracking_emit),
        )

        with ExitStack() as stack:
            for target, new_val in patches:
                stack.enter_context(patch(target, new_val))
            await handle_query(_make_event())

        assert "store_entities" in call_order, "store_entities was not called at all"
        assert "emit_query_response" in call_order, "_emit_event(query.response) was not called"

        store_idx = call_order.index("store_entities")
        emit_idx = call_order.index("emit_query_response")
        assert store_idx < emit_idx, (
            f"store_entities (pos {store_idx}) must be called BEFORE "
            f"emit_query_response (pos {emit_idx})"
        )

    @pytest.mark.asyncio
    async def test_no_entities_extracted_still_emits_response(self):
        """When extract_entities returns [], query.response is still emitted normally."""
        from query.handler import handle_query

        emit_mock = AsyncMock(return_value=None)
        patches = _build_patches(
            http_client_class=_make_http_client_class(),
            extract_entities_mock=AsyncMock(return_value=[]),
            embed_batch_mock=AsyncMock(return_value=[]),
            store_entities_mock=AsyncMock(return_value=None),
            emit_event_mock=emit_mock,
        )

        with ExitStack() as stack:
            for target, new_val in patches:
                stack.enter_context(patch(target, new_val))
            await handle_query(_make_event("What is the speed of light?"))

        response_calls = [
            c for c in emit_mock.call_args_list
            if c[0][0] == "query.response"
        ]
        assert len(response_calls) == 1

    @pytest.mark.asyncio
    async def test_entity_extraction_failure_does_not_suppress_response(self):
        """If extract_entities raises, query.response is still emitted (non-fatal)."""
        from query.handler import handle_query

        emit_mock = AsyncMock(return_value=None)
        patches = _build_patches(
            http_client_class=_make_http_client_class(),
            extract_entities_mock=AsyncMock(
                side_effect=RuntimeError("entity extraction API unavailable")
            ),
            embed_batch_mock=AsyncMock(return_value=[]),
            store_entities_mock=AsyncMock(return_value=None),
            emit_event_mock=emit_mock,
        )

        with ExitStack() as stack:
            for target, new_val in patches:
                stack.enter_context(patch(target, new_val))
            # Must not raise — extraction failure is non-fatal (D-159 Fix 1 constraint)
            await handle_query(_make_event("My name is Alice"))

        response_calls = [
            c for c in emit_mock.call_args_list
            if c[0][0] == "query.response"
        ]
        assert len(response_calls) == 1
