"""Tests for context assembly."""

from query.context import assemble

PERSONALITY = "You are CLIVE." * 10
ALIGNMENT = "Rule 1: No fabrication." * 5


def test_assemble_basic():
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=[{"role": "user", "content": "Hello"}],
        retrieved_chunks=[{"content": "Fact A", "source_attribution": "doc1", "relevance_score": 0.9}],
    )
    assert result.personality == PERSONALITY
    assert result.alignment_rules == ALIGNMENT
    assert len(result.conversation_history) >= 1
    assert len(result.retrieved_chunks) >= 1
    assert result.token_estimate > 0


def test_assemble_no_chunks():
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=[],
        retrieved_chunks=[],
    )
    assert result.retrieved_chunks == []
    assert result.conversation_history == []


def test_history_truncation():
    long_history = [{"role": "user", "content": "x" * 500}] * 50
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=long_history,
        retrieved_chunks=[],
    )
    # Should not include all 50 messages — truncated to budget
    assert len(result.conversation_history) < 50
