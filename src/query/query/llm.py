"""LiteLLM wrapper for Block 8.

D-077: provider abstracted via LiteLLM. Default provider is Anthropic.
Provider and model are configuration values, not code changes.

CLIVE_LLM_MODEL env var controls the model.
Examples:
  anthropic/claude-sonnet-4-20250514   (default)
  openai/gpt-4o
  anthropic/claude-opus-4-5
"""

from __future__ import annotations

import os
from typing import Any

import litellm
import structlog

log = structlog.get_logger()

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"


def get_model() -> str:
    return os.environ.get("CLIVE_LLM_MODEL", DEFAULT_MODEL)


async def complete(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
    user_query: str,
) -> str:
    """Call LLM with assembled context. Returns response text.

    Context structure (D-044 priority order):
      System prompt = personality (Tier 1) + alignment rules (Tier 2)
      Messages = conversation history (Tier 3) + current query with
                 retrieved context prepended (Tier 4)
    """
    model = get_model()

    system_prompt = f"{personality}\n\n---\n\n{alignment_rules}"

    # Prepend retrieved context to the current user query
    if retrieved_chunks:
        context_text = "\n\n".join(
            f"[Source: {c['source_attribution']}]\n{c['content']}"
            for c in retrieved_chunks
        )
        augmented_query = (
            f"Relevant context from your knowledge base:\n\n{context_text}"
            f"\n\n---\n\nQuery: {user_query}"
        )
    else:
        augmented_query = user_query

    messages = [
        *conversation_history,
        {"role": "user", "content": augmented_query},
    ]

    log.info("llm_call_start", model=model, history_turns=len(conversation_history))

    response = await litellm.acompletion(
        model=model,
        system=system_prompt,
        messages=messages,
        max_tokens=2048,
    )

    text = response.choices[0].message.content
    log.info("llm_call_complete", model=model, response_chars=len(text))
    return text
