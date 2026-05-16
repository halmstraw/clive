"""LiteLLM wrapper for Block 8.

D-077: provider abstracted via LiteLLM. Default provider is Anthropic.
Provider and model are configuration values, not code changes.

CLIVE_LLM_MODEL env var controls the completion model.
Examples:
  anthropic/claude-sonnet-4-20250514   (default)
  openai/gpt-4o
  anthropic/claude-opus-4-5

v0.6: complete() now returns (response_text, usage_data) so the handler
can record token counts and cost to clive_state.llm_usage (D-125).

v0.7: Block 11 full cross-session memory additions (D-128):
  - EMBEDDING_MODEL / embed() / embed_batch(): 1536-dim embeddings (D-096)
  - extract_entities(): lightweight LLM extraction pass post-response
  - summarise_turns(): LLM consolidation call with embedding for summaries
"""

from __future__ import annotations

import json
import os
from typing import Any

import litellm
import structlog

log = structlog.get_logger()

# Completion model — controlled by CLIVE_LLM_MODEL env var
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

# Embedding model — fixed per D-096 (text-embedding-3-small, 1536-dim)
EMBEDDING_MODEL = "openai/text-embedding-3-small"

# Valid entity types for extraction validation
_VALID_ENTITY_TYPES = {"person", "date", "preference", "commitment", "fact"}

# System prompt for entity extraction (kept concise — lightweight pass)
_EXTRACTION_SYSTEM_PROMPT = """You are a precise information extractor.
Given a conversation turn (USER message and ASSISTANT response), extract named facts
about the user that are worth remembering long-term.

Return a JSON object with an "entities" array. Each entity must have:
  entity_type: one of "person" | "date" | "preference" | "commitment" | "fact"
  key:         a short snake_case identifier (e.g. "colleague_name", "prefers_metric_units")
  value:       the extracted value as a short string

Return ONLY valid JSON. If no memorable facts are present, return {"entities": []}.

Examples of good extractions:
  "My colleague Sarah..." → {"entity_type":"person","key":"colleague_name","value":"Sarah"}
  "I prefer bullet points" → {"entity_type":"preference","key":"communication_style","value":"prefers bullet points"}
  "Meeting on Thursday at 2pm" → {"entity_type":"date","key":"upcoming_meeting","value":"Thursday at 2pm"}
  "I committed to finish the report by Friday" → {"entity_type":"commitment","key":"report_deadline","value":"Friday"}

Do NOT extract general knowledge, factual answers about the world, or temporary context."""


def get_model() -> str:
    return os.environ.get("CLIVE_LLM_MODEL", DEFAULT_MODEL)


# ── Completion ────────────────────────────────────────────────────────────────

async def complete(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
    user_query: str,
    memory_entities: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call LLM with assembled context.

    Returns (response_text, usage_data) where usage_data contains:
      model, prompt_tokens, completion_tokens

    Context structure (D-044 priority order):
      System prompt = personality (Tier 1) + alignment rules (Tier 2)
      Messages = conversation history (Tier 3) + current query with
                 memory entities (Tier 3.5) and retrieved context (Tier 4)
                 prepended (v0.7: D-128)
    """
    model = get_model()

    system_prompt = f"{personality}\n\n---\n\n{alignment_rules}"

    # Build augmented query sections in priority order
    sections: list[str] = []

    # Tier 3.5 — memory entities (v0.7, D-128)
    if memory_entities:
        lines = "\n".join(
            f"- {e['entity_type']} | {e['key']}: {e['value']}"
            for e in memory_entities
        )
        sections.append(f"[Memory — known facts and preferences about you]\n{lines}")

    # Tier 4 — retrieved knowledge chunks
    if retrieved_chunks:
        context_text = "\n\n".join(
            f"[Source: {c['source_attribution']}]\n{c['content']}"
            for c in retrieved_chunks
        )
        sections.append(f"[Relevant context from your knowledge base]\n\n{context_text}")

    if sections:
        preamble = "\n\n---\n\n".join(sections)
        augmented_query = f"{preamble}\n\n---\n\nQuery: {user_query}"
    else:
        augmented_query = user_query

    messages = [
        *conversation_history,
        {"role": "user", "content": augmented_query},
    ]

    log.info(
        "llm_call_start",
        model=model,
        history_turns=len(conversation_history),
        memory_entities=len(memory_entities) if memory_entities else 0,
    )

    response = await litellm.acompletion(
        model=model,
        system=system_prompt,
        messages=messages,
        max_tokens=2048,
    )

    text = response.choices[0].message.content

    # Extract token usage from LiteLLM response object
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    usage_data: dict[str, Any] = {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }

    log.info(
        "llm_call_complete",
        model=model,
        response_chars=len(text),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return text, usage_data


# ── Embeddings ────────────────────────────────────────────────────────────────

async def embed(text: str) -> list[float]:
    """Get a 1536-dim embedding for a single text via LiteLLM.

    Uses text-embedding-3-small (D-096, EMBEDDING_MODEL).
    Raises on failure — caller should catch and handle gracefully.

    Args:
        text: the text to embed.

    Returns:
        list of 1536 floats.
    """
    response = await litellm.aembedding(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0]["embedding"]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Get 1536-dim embeddings for a batch of texts.

    Returns parallel list of embeddings. Empty list in → empty list out.
    Raises on failure — caller should catch and handle gracefully.

    Args:
        texts: list of strings to embed.

    Returns:
        list of lists of 1536 floats, one per input text.
    """
    if not texts:
        return []
    response = await litellm.aembedding(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item["embedding"] for item in response.data]


# ── Entity extraction (v0.7 — D-128) ─────────────────────────────────────────

async def extract_entities(
    user_text: str,
    assistant_text: str,
) -> list[dict[str, Any]]:
    """Extract named entities from a conversation turn pair.

    Makes a lightweight LLM call with a structured extraction prompt.
    Returns a validated list of {entity_type, key, value} dicts.
    Returns [] on LLM error, JSON parse failure, or when no entities found.

    AC-2: called by handler.py after each successful response.

    Args:
        user_text:      the user's message in this turn.
        assistant_text: CLIVE's response in this turn.

    Returns:
        list of {entity_type, key, value} with entity_type validated against
        _VALID_ENTITY_TYPES.
    """
    model = get_model()
    turn_content = f"USER: {user_text}\n\nASSISTANT: {assistant_text}"

    try:
        response = await litellm.acompletion(
            model=model,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": turn_content}],
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fence if model wraps in ```json ... ```
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        entities_raw = parsed.get("entities", [])

        # Validate structure — drop any malformed entities silently
        valid: list[dict[str, Any]] = []
        for e in entities_raw:
            if (
                isinstance(e, dict)
                and e.get("entity_type") in _VALID_ENTITY_TYPES
                and isinstance(e.get("key"), str)
                and e["key"].strip()
                and isinstance(e.get("value"), str)
                and e["value"].strip()
            ):
                valid.append({
                    "entity_type": e["entity_type"],
                    "key": e["key"].strip(),
                    "value": e["value"].strip(),
                })

        log.info("entities_extracted", count=len(valid))
        return valid

    except Exception as exc:
        log.warning("entity_extraction_failed", error=str(exc))
        return []


# ── Consolidation summarisation (v0.7 — D-128) ───────────────────────────────

async def summarise_turns(turn_text: str) -> tuple[str, list[float]]:
    """Summarise a block of conversation turns into a compact summary with embedding.

    Used by memory.consolidate_if_needed (AC-5).
    Returns (summary_text, embedding) where embedding is 1536-dim.

    On LLM failure: returns a fallback summary and still embeds it (best effort).

    Args:
        turn_text: newline-joined conversation turns (ROLE: content format).

    Returns:
        (summary_text, embedding_vector)
    """
    model = get_model()
    _summarise_system = (
        "You are a memory consolidator. "
        "Summarise the following conversation turns into a compact paragraph "
        "capturing key facts, preferences, commitments, and named entities "
        "mentioned. Be concise — aim for 2–4 sentences."
    )

    try:
        response = await litellm.acompletion(
            model=model,
            system=_summarise_system,
            messages=[{"role": "user", "content": turn_text}],
            max_tokens=400,
        )
        summary = response.choices[0].message.content.strip()
    except Exception as exc:
        log.error("summarise_turns_llm_failed", error=str(exc))
        line_count = len(turn_text.splitlines())
        summary = f"[Consolidation summary unavailable — {line_count} turns compressed]"

    try:
        embedding = await embed(summary)
    except Exception as exc:
        log.error("summarise_turns_embed_failed", error=str(exc))
        embedding = [0.0] * 1536  # zero vector fallback — won't match on search

    return summary, embedding
