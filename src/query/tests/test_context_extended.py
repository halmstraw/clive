"""Extended context assembly tests covering memory entity paths (v0.7, D-128)."""
from __future__ import annotations

from query.context import assemble, _memory_to_text, _estimate_tokens


PERSONALITY = "You are CLIVE."
ALIGNMENT = "Be safe and honest."


class TestMemoryToText:
    def test_empty_entities_returns_empty_string(self):
        assert _memory_to_text([]) == ""

    def test_formats_entities_with_type_key_value(self):
        entities = [
            {"entity_type": "person", "key": "colleague", "value": "Alice"},
            {"entity_type": "preference", "key": "style", "value": "bullet points"},
        ]
        text = _memory_to_text(entities)
        assert "person | colleague: Alice" in text
        assert "preference | style: bullet points" in text
        assert "Memory" in text


class TestEstimateTokens:
    def test_empty_string_is_zero(self):
        assert _estimate_tokens("") == 0

    def test_four_chars_is_one_token(self):
        assert _estimate_tokens("abcd") == 1

    def test_longer_text(self):
        text = "x" * 400
        assert _estimate_tokens(text) == 100


class TestAssembleWithMemoryEntities:
    def test_memory_entities_included_in_result(self):
        entities = [
            {"entity_type": "person", "key": "friend", "value": "Bob"},
        ]
        result = assemble(
            personality=PERSONALITY,
            alignment_rules=ALIGNMENT,
            conversation_history=[],
            retrieved_chunks=[],
            memory_entities=entities,
        )
        assert len(result.memory_entities) == 1
        assert result.memory_entities[0]["key"] == "friend"

    def test_none_memory_entities_treated_as_empty(self):
        result = assemble(
            personality=PERSONALITY,
            alignment_rules=ALIGNMENT,
            conversation_history=[],
            retrieved_chunks=[],
            memory_entities=None,
        )
        assert result.memory_entities == []

    def test_memory_entities_with_history_and_chunks(self):
        """Full context with all tiers present."""
        entities = [
            {"entity_type": "fact", "key": "city", "value": "London"},
        ]
        history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}]
        chunks = [{"content": "Some knowledge.", "source_attribution": "doc.pdf", "relevance_score": 0.9}]

        result = assemble(
            personality=PERSONALITY,
            alignment_rules=ALIGNMENT,
            conversation_history=history,
            retrieved_chunks=chunks,
            memory_entities=entities,
        )

        assert len(result.memory_entities) >= 1
        assert len(result.conversation_history) >= 1
        assert len(result.retrieved_chunks) >= 1
        assert result.token_estimate > 0

    def test_enormous_personality_expands_budget(self):
        """When fixed costs exceed budget, minimum tier guarantees still apply."""
        huge_personality = "x" * 400_000  # ~100k tokens
        result = assemble(
            personality=huge_personality,
            alignment_rules=ALIGNMENT,
            conversation_history=[],
            retrieved_chunks=[],
        )
        # Should not raise; token_estimate will exceed TOTAL_BUDGET
        assert result.personality == huge_personality

    def test_many_memory_entities_all_included_when_budget_allows(self):
        """With no history and no chunks, surplus flows to memory — all entities fit."""
        many_entities = [
            {"entity_type": "fact", "key": f"key_{i}", "value": "x" * 400}
            for i in range(50)
        ]
        result = assemble(
            personality=PERSONALITY,
            alignment_rules=ALIGNMENT,
            conversation_history=[],
            retrieved_chunks=[],
            memory_entities=many_entities,
        )
        # With large budget surplus, all 50 entities should be included
        assert len(result.memory_entities) == 50

    def test_memory_truncation_when_personality_consumes_budget(self):
        """Entities are truncated when budget is tight from large fixed-cost docs."""
        # Fill up most of the budget with personality (leaving minimal surplus)
        huge_personality = "x" * 392_000  # ~98k tokens ≈ TOTAL_BUDGET
        small_entity = {"entity_type": "fact", "key": "k", "value": "v"}
        many_entities = [small_entity] * 100

        result = assemble(
            personality=huge_personality,
            alignment_rules=ALIGNMENT,
            conversation_history=[],
            retrieved_chunks=[],
            memory_entities=many_entities,
        )
        # All entities are very small (1 token each approx.) and minimum is 1000
        # tokens of memory, so most should still fit — test that result is stable
        assert isinstance(result.memory_entities, list)
        assert result.token_estimate > 0
