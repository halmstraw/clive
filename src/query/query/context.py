"""Context window assembly for Block 8.

D-044: dynamic allocation with priority ordering.
  Tier 1: personality document (always present, takes what it needs)
  Tier 2: alignment rules (always present, takes what it needs)
  Tier 3: conversation history (minimum guaranteed, surplus if available)
  Tier 4: retrieved knowledge chunks (minimum guaranteed, surplus if available)

Token budget values are conservative defaults. Adjust based on
actual document sizes once personality and alignment docs are loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Total token budget for LLM context
# Default: 100k tokens (Claude claude-sonnet-4-20250514 supports 200k)
# Reserved: ~2k for the query itself and response overhead
TOTAL_BUDGET = 98_000

# Tier 3 and 4 minimum guarantees (tokens)
MIN_HISTORY_TOKENS = 2_000
MIN_RETRIEVAL_TOKENS = 4_000

# Approximate tokens per character (rough estimate; real count uses tiktoken)
CHARS_PER_TOKEN = 4


@dataclass
class AssembledContext:
    personality: str
    alignment_rules: str
    conversation_history: list[dict[str, str]]
    retrieved_chunks: list[dict[str, Any]]
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _chunks_to_text(chunks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[Source: {c['source_attribution']}]\n{c['content']}"
        for c in chunks
    )


def assemble(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
) -> AssembledContext:
    """Assemble context respecting D-044 priority ordering.

    Tiers 1 and 2 always included in full.
    Remaining budget split between tiers 3 and 4 with minimums.
    Surplus flows to whichever tier has more content.
    """
    # Fixed costs (Tiers 1 and 2)
    personality_tokens = _estimate_tokens(personality)
    alignment_tokens = _estimate_tokens(alignment_rules)
    fixed_cost = personality_tokens + alignment_tokens

    remaining = TOTAL_BUDGET - fixed_cost
    if remaining < MIN_HISTORY_TOKENS + MIN_RETRIEVAL_TOKENS:
        # Pathological case: personality/alignment docs are enormous
        # Include minimums only and truncate if needed
        remaining = MIN_HISTORY_TOKENS + MIN_RETRIEVAL_TOKENS

    # Calculate available for Tier 3 and 4
    history_text = _format_history(conversation_history)
    chunks_text = _chunks_to_text(retrieved_chunks)

    history_tokens_needed = _estimate_tokens(history_text)
    chunks_tokens_needed = _estimate_tokens(chunks_text)

    # Allocate with minimums and surplus flow
    surplus = remaining - MIN_HISTORY_TOKENS - MIN_RETRIEVAL_TOKENS
    surplus = max(0, surplus)

    history_surplus = max(0, history_tokens_needed - MIN_HISTORY_TOKENS)
    chunks_surplus = max(0, chunks_tokens_needed - MIN_RETRIEVAL_TOKENS)
    total_surplus_needed = history_surplus + chunks_surplus

    if total_surplus_needed > 0:
        history_alloc = MIN_HISTORY_TOKENS + int(
            surplus * history_surplus / total_surplus_needed
        )
        chunks_alloc = remaining - history_alloc
    else:
        history_alloc = MIN_HISTORY_TOKENS
        chunks_alloc = remaining - history_alloc

    # Truncate to allocation
    final_history = _truncate_history(conversation_history, history_alloc)
    final_chunks = _truncate_chunks(retrieved_chunks, chunks_alloc)

    total_estimate = fixed_cost + history_alloc + chunks_alloc

    return AssembledContext(
        personality=personality,
        alignment_rules=alignment_rules,
        conversation_history=final_history,
        retrieved_chunks=final_chunks,
        token_estimate=total_estimate,
    )


def _format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in history)


def _truncate_history(
    history: list[dict[str, str]], token_budget: int
) -> list[dict[str, str]]:
    """Keep most recent messages that fit within budget."""
    result = []
    tokens_used = 0
    for msg in reversed(history):
        msg_tokens = _estimate_tokens(msg["content"])
        if tokens_used + msg_tokens > token_budget:
            break
        result.insert(0, msg)
        tokens_used += msg_tokens
    return result


def _truncate_chunks(
    chunks: list[dict[str, Any]], token_budget: int
) -> list[dict[str, Any]]:
    """Include highest-relevance chunks that fit within budget."""
    result = []
    tokens_used = 0
    for chunk in chunks:  # Already sorted by relevance
        chunk_tokens = _estimate_tokens(chunk["content"])
        if tokens_used + chunk_tokens > token_budget:
            break
        result.append(chunk)
        tokens_used += chunk_tokens
    return result
