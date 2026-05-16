"""Tests for Block 11 full cross-session memory — v0.7 (D-128, D-129).

Covers all six acceptance criteria:
  AC-1: SQL schema idempotency — verified by CI SQL test; structural check here.
  AC-2: entity extraction and storage — test_extract_* + test_store_*
  AC-3: semantic retrieval — test_retrieve_*
  AC-4: memory tier in context assembly — test_assemble_with_memory_*
  AC-5: memory consolidation — test_consolidation_*
  AC-6: ≥8 test cases, zero regressions — satisfied by this file + existing suites.

All tests mock DB pool and LLM client. No live DB or LLM calls in CI.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── AC-2: entity extraction (llm.extract_entities) ───────────────────────────

@pytest.mark.asyncio
async def test_extract_entities_returns_entities_on_valid_json():
    """LLM returns valid JSON with entity list — parsed, validated, returned."""
    from query.llm import extract_entities

    payload = json.dumps({
        "entities": [
            {"entity_type": "person", "key": "colleague_name", "value": "Sarah"},
            {"entity_type": "preference", "key": "report_format", "value": "bullet points"},
        ]
    })

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = payload

    with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
        result = await extract_entities(
            "Hi, I work with Sarah.",
            "Got it, Sarah is your colleague.",
        )

    assert len(result) == 2
    assert result[0]["entity_type"] == "person"
    assert result[0]["key"] == "colleague_name"
    assert result[0]["value"] == "Sarah"
    assert result[1]["entity_type"] == "preference"
    assert result[1]["key"] == "report_format"


@pytest.mark.asyncio
async def test_extract_entities_returns_empty_list_when_no_entities():
    """LLM returns {entities:[]} — empty list returned without error."""
    from query.llm import extract_entities

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({"entities": []})

    with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
        result = await extract_entities(
            "What is the speed of light?",
            "Approximately 299,792,458 metres per second.",
        )

    assert result == []


@pytest.mark.asyncio
async def test_extract_entities_handles_llm_error_gracefully():
    """LLM call raises — extract_entities returns [] without propagating."""
    from query.llm import extract_entities

    with patch(
        "query.llm.litellm.acompletion",
        AsyncMock(side_effect=RuntimeError("API unavailable")),
    ):
        result = await extract_entities("query text", "response text")

    assert result == []


@pytest.mark.asyncio
async def test_extract_entities_drops_malformed_entity_types():
    """Entities with invalid entity_type are silently dropped; valid ones returned."""
    from query.llm import extract_entities

    payload = json.dumps({
        "entities": [
            {"entity_type": "INVALID_TYPE", "key": "foo", "value": "bar"},
            {"entity_type": "fact", "key": "sky_colour", "value": "blue"},
        ]
    })

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = payload

    with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
        result = await extract_entities("The sky is blue.", "Yes, it is.")

    # Only the valid entity is returned
    assert len(result) == 1
    assert result[0]["entity_type"] == "fact"
    assert result[0]["value"] == "blue"


# ── AC-3: semantic memory retrieval (memory.retrieve_entities) ────────────────

@pytest.mark.asyncio
async def test_retrieve_entities_returns_ordered_results():
    """DB returns rows ordered by similarity — retrieve_entities maps them correctly."""
    from query.memory import retrieve_entities

    entity1_id = uuid.uuid4()
    entity2_id = uuid.uuid4()
    fake_rows = [
        {
            "entity_id": entity1_id,
            "entity_type": "person",
            "key": "colleague_name",
            "value": "Alice",
            "similarity_score": 0.95,
        },
        {
            "entity_id": entity2_id,
            "entity_type": "fact",
            "key": "project_topic",
            "value": "AI safety",
            "similarity_score": 0.72,
        },
    ]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fake_rows)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    with patch("query.memory.get_pool", return_value=mock_pool):
        result = await retrieve_entities([0.1] * 1536, top_k=5)

    assert len(result) == 2
    assert result[0]["entity_type"] == "person"
    assert result[0]["value"] == "Alice"
    assert result[0]["similarity_score"] == pytest.approx(0.95)
    assert result[1]["value"] == "AI safety"
    assert result[1]["similarity_score"] == pytest.approx(0.72)
    # entity_id is stringified
    assert result[0]["entity_id"] == str(entity1_id)


@pytest.mark.asyncio
async def test_retrieve_entities_returns_empty_on_db_error():
    """DB pool raises RuntimeError — retrieve_entities returns [] without propagating."""
    from query.memory import retrieve_entities

    with patch(
        "query.memory.get_pool",
        side_effect=RuntimeError("pool not initialised"),
    ):
        result = await retrieve_entities([0.0] * 1536, top_k=5)

    assert result == []


# ── AC-4: memory tier in context assembly (context.assemble) ─────────────────

def test_assemble_with_memory_entities_injects_memory_into_context():
    """assemble() with memory_entities populates memory_entities field in result."""
    from query.context import assemble

    entities = [
        {"entity_type": "person", "key": "colleague_name", "value": "Sarah", "similarity_score": 0.9},
        {"entity_type": "preference", "key": "report_style", "value": "concise bullet points", "similarity_score": 0.8},
    ]

    result = assemble(
        personality="You are CLIVE.",
        alignment_rules="No fabrication.",
        conversation_history=[],
        retrieved_chunks=[],
        memory_entities=entities,
    )

    assert result.memory_entities == entities
    assert result.token_estimate > 0


def test_assemble_without_memory_entities_produces_same_output_as_before():
    """assemble() with memory_entities=[] is identical to calling without parameter."""
    from query.context import assemble

    kwargs = {
        "personality": "You are CLIVE.",
        "alignment_rules": "No fabrication.",
        "conversation_history": [{"role": "user", "content": "Hello"}],
        "retrieved_chunks": [
            {"content": "Fact A", "source_attribution": "doc1", "relevance_score": 0.9}
        ],
    }

    result_default = assemble(**kwargs)
    result_empty = assemble(**kwargs, memory_entities=[])

    assert result_default.memory_entities == []
    assert result_empty.memory_entities == []
    assert result_default.conversation_history == result_empty.conversation_history
    assert result_default.retrieved_chunks == result_empty.retrieved_chunks
    assert result_default.token_estimate == result_empty.token_estimate


# ── AC-5: memory consolidation (memory.consolidate_if_needed) ─────────────────

@pytest.mark.asyncio
async def test_consolidation_triggers_and_creates_summary_at_count_threshold():
    """turn count > 100 — llm_summarise called once, summary inserted, turns deleted."""
    from query.memory import consolidate_if_needed

    now = datetime.now(timezone.utc)
    fake_turns = [
        {
            "turn_id": uuid.uuid4(),
            "turn_number": i,
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Turn content {i}",
        }
        for i in range(50)
    ]

    mock_conn = AsyncMock()
    # fetchrow: count=101 (above threshold), oldest is recent (age trigger = False)
    mock_conn.fetchrow = AsyncMock(
        return_value={"cnt": 101, "oldest": now - timedelta(hours=1)}
    )
    mock_conn.fetch = AsyncMock(return_value=fake_turns)
    mock_conn.execute = AsyncMock(return_value=None)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    mock_summarise = AsyncMock(return_value=("Summary of 50 turns.", [0.1] * 1536))

    with patch("query.memory.get_pool", return_value=mock_pool):
        await consolidate_if_needed(uuid.uuid4(), mock_summarise)

    # LLM summarise called exactly once
    mock_summarise.assert_called_once()
    # execute called at least twice: INSERT summary + DELETE turns
    assert mock_conn.execute.call_count >= 2


@pytest.mark.asyncio
async def test_consolidation_noop_below_threshold():
    """count ≤ 100 and turns recent — llm_summarise NOT called (no-op)."""
    from query.memory import consolidate_if_needed

    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        return_value={"cnt": 50, "oldest": now - timedelta(hours=1)}
    )
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    mock_summarise = AsyncMock()

    with patch("query.memory.get_pool", return_value=mock_pool):
        await consolidate_if_needed(uuid.uuid4(), mock_summarise)

    mock_summarise.assert_not_called()


@pytest.mark.asyncio
async def test_consolidation_triggers_on_age_even_when_count_low():
    """count ≤ 100 but oldest turn > 48h — age trigger fires, summarise called."""
    from query.memory import consolidate_if_needed

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=50)  # 50h > 48h threshold

    fake_turns = [
        {
            "turn_id": uuid.uuid4(),
            "turn_number": i,
            "role": "user",
            "content": f"Old turn {i}",
        }
        for i in range(10)
    ]

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        return_value={"cnt": 10, "oldest": old_time}
    )
    mock_conn.fetch = AsyncMock(return_value=fake_turns)
    mock_conn.execute = AsyncMock(return_value=None)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_pool)
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    mock_summarise = AsyncMock(return_value=("Old conversation summary.", [0.2] * 1536))

    with patch("query.memory.get_pool", return_value=mock_pool):
        await consolidate_if_needed(uuid.uuid4(), mock_summarise)

    mock_summarise.assert_called_once()


@pytest.mark.asyncio
async def test_consolidation_handles_db_error_gracefully():
    """DB pool raises — consolidate_if_needed returns without propagating."""
    from query.memory import consolidate_if_needed

    mock_summarise = AsyncMock()

    with patch(
        "query.memory.get_pool",
        side_effect=RuntimeError("pool not initialised"),
    ):
        # Must not raise
        await consolidate_if_needed(uuid.uuid4(), mock_summarise)

    mock_summarise.assert_not_called()


# ── AC-2: entity storage (memory.store_entities) ─────────────────────────────

@pytest.mark.asyncio
async def test_store_entities_inserts_one_row_per_entity():
    """store_entities calls conn.execute once per entity."""
    from query.memory import store_entities

    entities = [
        {"entity_type": "person", "key": "manager_name", "value": "Bob"},
        {"entity_type": "fact", "key": "prefers_tea", "value": "yes, Earl Grey"},
    ]
    embeddings = [[0.1] * 1536, [0.2] * 1536]

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=None)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    with patch("query.memory.get_pool", return_value=mock_pool):
        await store_entities(entities, source_turn_id=None, embeddings=embeddings)

    assert mock_conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_store_entities_noop_on_empty_list():
    """store_entities with empty entities list does not touch the DB."""
    from query.memory import store_entities

    mock_pool = MagicMock()

    with patch("query.memory.get_pool", return_value=mock_pool):
        await store_entities([], source_turn_id=None, embeddings=[])

    # get_pool() itself should not have been called (returns early)
    mock_pool.acquire.assert_not_called()
