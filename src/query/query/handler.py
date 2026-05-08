"""Core query handler for Block 8.

Receives query.received event, assembles context, calls LLM,
emits query.response. Handles action-intent queries (D-045).
Idempotent via response cache (D-046).
Confidence signal is retrieval quality only (D-047).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

from . import context as ctx
from . import llm
from .idempotency import cache

log = structlog.get_logger()

# Action-intent keywords — simple heuristic for v0.1
# Evolves post-v0.1 via Block 21
ACTION_VERBS = {
    "send", "email", "message", "book", "schedule", "create",
    "delete", "update", "post", "call", "order", "buy", "pay",
    "remind", "set", "add", "remove", "cancel", "upload",
}

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")


async def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Submit event to Block 13 via HTTP.

    At v0.1, Block 8 and Block 13 communicate via the in-process
    bus in the orchestrator container. Block 8 is a separate container
    and submits events via HTTP to Block 13's event intake endpoint.
    Block 13 then routes via its internal bus.
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ORCHESTRATOR_URL}/events",
            json={"event_type": event_type, "source_block": 8, **payload},
            timeout=10.0,
        )


def _detect_action_intent(text: str) -> str | None:
    """Heuristic: detect if query implies an action CLIVE cannot perform.

    Returns the detected action verb or None.
    """
    words = text.lower().split()
    for word in words:
        if word in ACTION_VERBS:
            return word
    return None


def _compute_confidence(
    ranked_chunks: list[dict[str, Any]],
    relevance_threshold: float = 0.3,
) -> dict[str, Any]:
    """Compute retrieval quality confidence signal — D-047."""
    chunk_count = len(ranked_chunks)
    max_score = max((c["relevance_score"] for c in ranked_chunks), default=0.0)
    threshold_met = max_score >= relevance_threshold
    return {
        "chunks_returned": chunk_count,
        "highest_relevance_score": max_score,
        "threshold_met": threshold_met,
    }


async def handle_query(event: dict[str, Any]) -> None:
    """Handle a query.received event.

    1. Check idempotency cache (D-046)
    2. Retrieve knowledge via orchestrator (D-043)
    3. Check for action intent (D-045)
    4. Assemble context (D-044)
    5. Call LLM (D-077)
    6. Emit query.response
    """
    event_id = uuid.UUID(event["event_id"])
    conversation_id = uuid.UUID(event["conversation_id"])
    user_input = event["input_text"]
    zone_scope = event.get("zone_scope", "personal")

    # 1. Idempotency check — D-046
    cached = cache.get(conversation_id, event_id)
    if cached:
        log.info("idempotency_cache_hit", event_id=str(event_id))
        await _emit_event("query.response", {**cached, "conversation_id": str(conversation_id)})
        return

    # 2. Check for action intent — D-045
    action_verb = _detect_action_intent(user_input)
    if action_verb:
        log.info("action_intent_detected", verb=action_verb)
        await _emit_event(
            "action.requested_unavailable",
            {
                "conversation_id": str(conversation_id),
                "event_id": str(event_id),
                "recognised_action_type": action_verb,
                "original_query_context": user_input,
            },
        )
        # Still respond — acknowledge and offer what we can do
        response_text = (
            f"I can see you want to {action_verb} something — "
            "actions aren't available yet. I can answer questions "
            "and search my knowledge base. What would you like to know?"
        )
        response_payload = {
            "event_id": str(event_id),
            "response_text": response_text,
            "confidence": {"chunks_returned": 0, "highest_relevance_score": 0.0, "threshold_met": False},
        }
        cache.set(conversation_id, event_id, response_payload)
        await _emit_event("query.response", {**response_payload, "conversation_id": str(conversation_id)})
        return

    # 3. Retrieve system documents via orchestrator (D-043, D-048)
    async with httpx.AsyncClient() as client:
        personality_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/system-document",
            json={"document_type": "personality", "zone_scope": zone_scope},
            timeout=10.0,
        )
        personality_resp.raise_for_status()
        personality_doc = personality_resp.json()["document_content"]

        alignment_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/system-document",
            json={"document_type": "alignment_rules", "zone_scope": zone_scope},
            timeout=10.0,
        )
        alignment_resp.raise_for_status()
        alignment_doc = alignment_resp.json()["document_content"]

    # 4. Retrieve knowledge chunks via orchestrator (D-043)
    async with httpx.AsyncClient() as client:
        retrieval_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/knowledge",
            json={
                "retrieval_query": user_input,
                "zone_scope": zone_scope,
                "result_limit": 20,
                "conversation_id": str(conversation_id),
            },
            timeout=15.0,
        )
        retrieval_resp.raise_for_status()
        retrieval_result = retrieval_resp.json()

    ranked_chunks = retrieval_result.get("ranked_chunks", [])
    confidence = _compute_confidence(ranked_chunks)

    # 5. Retrieve conversation history from event payload
    conversation_history = event.get("conversation_history", [])

    # 6. Assemble context (D-044)
    assembled = ctx.assemble(
        personality=personality_doc,
        alignment_rules=alignment_doc,
        conversation_history=conversation_history,
        retrieved_chunks=ranked_chunks,
    )

    # 7. Call LLM (D-077)
    response_text = await llm.complete(
        personality=assembled.personality,
        alignment_rules=assembled.alignment_rules,
        conversation_history=assembled.conversation_history,
        retrieved_chunks=assembled.retrieved_chunks,
        user_query=user_input,
    )

    # 8. Build response and cache it
    response_payload = {
        "event_id": str(event_id),
        "response_text": response_text,
        "confidence": confidence,
    }
    cache.set(conversation_id, event_id, response_payload)

    # 9. Emit query.response
    await _emit_event(
        "query.response",
        {**response_payload, "conversation_id": str(conversation_id)},
    )

    log.info(
        "query_handled",
        event_id=str(event_id),
        chunks_used=len(assembled.retrieved_chunks),
        threshold_met=confidence["threshold_met"],
    )
