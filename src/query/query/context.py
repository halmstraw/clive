"""Context window assembly for Block 8.

D-044: dynamic allocation with priority ordering.
  Tier 1: personality document (always present, takes what it needs)
  Tier 2: alignment rules (always present, takes what it needs)
  Tier 3: conversation history (minimum guaranteed, surplus if available)
  Tier 3.5: memory entities — v0.7 D-128 (minimum guaranteed, surplus if available)
  Tier 4: retrieved knowledge chunks (minimum guaranteed, surplus if available)

Token budget values are conservative defaults. Adjust based on
actual document sizes once personality and alignment docs are loaded.

v0.7 (D-128): memory_entities parameter added to assemble(). AssembledContext
extended with memory_entities field. Three-tier dynamic allocation replaces
two-tier for Tiers 3, 3.5, and 4. Calling assemble() without memory_entities
(or with memory_entities=[]) produces identical output to pre-v0.7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Total token budget for LLM context
# Default: 100k tokens (Claude claude-sonnet-4-20250514 supports 200k)
# Reserved: ~2k for the query itself and response overhead
TOTAL_BUDGET = 98_000

# Tier 3, 3.5, and 4 minimum guarantees (tokens)
MIN_HISTORY_TOKENS = 2_000
MIN_MEMORY_TOKENS = 1_000   # D-128: memory entities tier (AC-4)
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
    memory_entities: list[dict[str, Any]] = field(default_factory=list)


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _chunks_to_text(chunks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[Source: {c['source_attribution']}]\n{c['content']}"
        for c in chunks
    )


def _memory_to_text(entities: list[dict[str, Any]]) -> str:
    """Format memory entities into the text they will occupy in context."""
    if not entities:
        return ""
    lines = "\n".join(
        f"- {e['entity_type']} | {e['key']}: {e['value']}"
        for e in entities
    )
    return f"[Memory — known facts and preferences about you]\n{lines}"


def assemble(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
    memory_entities: list[dict[str, Any]] | None = None,
) -> AssembledContext:
    """Assemble context respecting D-044 priority ordering (extended for v0.7).

    Tiers 1 and 2 always included in full.
    Remaining budget split between tiers 3, 3.5, and 4 with minimums.
    Surplus flows proportionally to whichever tiers have more content.

    Calling with memory_entities=[] or without memory_entities produces output
    identical to pre-v0.7 behaviour (AC-4 no-regression requirement).

    Args:
        personality:          Tier 1 — full personality document.
        alignment_rules:      Tier 2 — full alignment rules document.
        conversation_history: Tier 3 — recent conversation turns (list of {role, content}).
        retrieved_chunks:     Tier 4 — ranked knowledge chunks from Block 16.
        memory_entities:      Tier 3.5 — entities from memory retrieval (v0.7, D-128).
                              Defaults to [] when omitted.

    Returns:
        AssembledContext with all tiers truncated to their allocated budgets.
    """
    if memory_entities is None:
        memory_entities = []

    # Fixed costs (Tiers 1 and 2 — always included in full)
    personality_tokens = _estimate_tokens(personality)
    alignment_tokens = _estimate_tokens(alignment_rules)
    fixed_cost = personality_tokens + alignment_tokens

    remaining = TOTAL_BUDGET - fixed_cost
    total_min = MIN_HISTORY_TOKENS + MIN_MEMORY_TOKENS + MIN_RETRIEVAL_TOKENS
    if remaining < total_min:
        # Pathological case: personality/alignment docs are enormous
        remaining = total_min

    # Estimate token needs for Tiers 3, 3.5, and 4
    history_text = _format_history(conversation_history)
    memory_text = _memory_to_text(memory_entities)
    chunks_text = _chunks_to_text(retrieved_chunks)

    history_tokens_needed = _estimate_tokens(history_text)
    memory_tokens_needed = _estimate_tokens(memory_text)
    chunks_tokens_needed = _estimate_tokens(chunks_text)

    # Allocate with minimums and proportional surplus flow
    surplus = max(0, remaining - total_min)

    history_surplus = max(0, history_tokens_needed - MIN_HISTORY_TOKENS)
    memory_surplus = max(0, memory_tokens_needed - MIN_MEMORY_TOKENS)
    chunks_surplus = max(0, chunks_tokens_needed - MIN_RETRIEVAL_TOKENS)
    total_surplus_needed = history_surplus + memory_surplus + chunks_surplus

    if total_surplus_needed > 0:
        history_alloc = MIN_HISTORY_TOKENS + int(
            surplus * history_surplus / total_surplus_needed
        )
        memory_alloc = MIN_MEMORY_TOKENS + int(
            surplus * memory_surplus / total_surplus_needed
        )
        chunks_alloc = remaining - history_alloc - memory_alloc
    else:
        history_alloc = MIN_HISTORY_TOKENS
        memory_alloc = MIN_MEMORY_TOKENS
        chunks_alloc = remaining - history_alloc - memory_alloc

    # Truncate each tier to its allocation
    final_history = _truncate_history(conversation_history, history_alloc)
    final_memory = _truncate_memory_entities(memory_entities, memory_alloc)
    final_chunks = _truncate_chunks(retrieved_chunks, chunks_alloc)

    total_estimate = fixed_cost + history_alloc + memory_alloc + chunks_alloc

    return AssembledContext(
        personality=personality,
        alignment_rules=alignment_rules,
        conversation_history=final_history,
        memory_entities=final_memory,
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


def _truncate_memory_entities(
    entities: list[dict[str, Any]], token_budget: int
) -> list[dict[str, Any]]:
    """Include as many memory entities as fit within budget (highest similarity first).

    Entities are assumed to arrive in similarity order (retrieve_entities returns
    closest-first). We truncate from the tail to preserve highest-relevance entities.
    """
    if not entities:
        return []
    result: list[dict[str, Any]] = []
    # Account for section header tokens
    tokens_used = _estimate_tokens("[Memory — known facts and preferences about you]\n")
    for entity in entities:
        line = f"- {entity['entity_type']} | {entity['key']}: {entity['value']}\n"
        entity_tokens = _estimate_tokens(line)
        if tokens_used + entity_tokens > token_budget:
            break
        result.append(entity)
        tokens_used += entity_tokens
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
