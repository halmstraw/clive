"""Core query handler for Block 8.

Receives query.received event, assembles context, calls LLM,
emits query.response. Handles action-intent queries (D-045).
Idempotent via response cache (D-046).
Confidence signal is retrieval quality only (D-047).

v0.3: query.response payload now includes chunk_ids (list of chunk UUIDs
returned in this retrieval). Block 18 (Feedback) uses this to tag the
specific chunks that were poor quality.

v0.5: prometheus_client instrumentation added (D-122 Phase 2).

v0.6: Block 20 spend cap gate and LLM usage recording (D-125).
  - Before each LLM call: check today's spend against DAILY_SPEND_CAP_USD.
  - If cap exceeded: return canned response, emit cost.cap_exceeded, no LLM call.
  - After each LLM call: record model/tokens/cost to clive_state.llm_usage.
  - Prometheus: increment clive_llm_tokens_total and clive_llm_cost_usd_total.

v0.7: Block 11 full cross-session memory (D-128).
  - After spend cap check: embed query, retrieve top-5 memory entities (AC-3).
  - Memory entities injected as Tier 3.5 in context assembly (AC-4).
  - Post-response: extract entities from turn, store with embeddings (AC-2).
  - Post-response: run consolidation if turn count/age threshold met (AC-5).
  - All memory operations are non-fatal (caught exceptions → graceful degradation).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx
import structlog

from . import context as ctx
from . import llm
from . import memory
from .idempotency import cache
from .metrics import (
    llm_cost_cap_exceeded_total,
    llm_cost_usd_total,
    llm_tokens_total,
    queries_total,
    query_duration_seconds,
    retrieval_chunks_returned_total,
)
from .spend import compute_cost, get_daily_cap, get_today_spend_usd, record_usage

log = structlog.get_logger()

# Action-intent keywords — simple heuristic for v0.1
# Evolves post-v0.1 via Block 21
ACTION_VERBS = {
    "send", "email", "message", "book", "schedule", "create",
    "delete", "update", "post", "call", "order", "buy", "pay",
    "remind", "set", "add", "remove", "cancel", "upload",
}

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")
_EVENT_QUERY_RESPONSE = "query.response"


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

    Steps:
    1.  Idempotency check (D-046)
    2.  Action intent check (D-045)
    3.  Retrieve system documents via orchestrator (D-043, D-048)
    4.  Retrieve knowledge chunks via orchestrator (D-043)
    5.  Retrieve conversation history from event payload
    6.  Spend cap check — return canned response if exceeded (D-125)
    7.  Semantic memory retrieval (v0.7, D-128, AC-3)
    8.  Assemble context (D-044) — includes memory entities as Tier 3.5
    9.  Call LLM (D-077)
    10. Record LLM usage to clive_state.llm_usage (D-125)
    11. Build response payload, cache, emit query.response (v0.3: include chunk_ids)
    12. Record query duration (D-122 Phase 2)
    13. Post-response memory operations (v0.7, D-128) — non-fatal:
        a. Extract entities from the turn (AC-2)
        b. Store entities with embeddings (AC-2)
        c. Consolidate old turns if threshold met (AC-5)
    """
    start_time = time.monotonic()

    event_id = uuid.UUID(event["event_id"])
    conversation_id = uuid.UUID(event["conversation_id"])
    user_input = event["input_text"]
    zone_scope = event.get("zone_scope", "personal")

    # Increment query counter (D-122 Phase 2)
    queries_total.inc()

    # 1. Idempotency check — D-046
    cached = cache.get(conversation_id, event_id)
    if cached:
        log.info("idempotency_cache_hit", event_id=str(event_id))
        await _emit_event(_EVENT_QUERY_RESPONSE, {**cached, "conversation_id": str(conversation_id)})
        query_duration_seconds.observe(time.monotonic() - start_time)
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
            "chunk_ids": [],  # No retrieval performed
        }
        cache.set(conversation_id, event_id, response_payload)
        await _emit_event(_EVENT_QUERY_RESPONSE, {**response_payload, "conversation_id": str(conversation_id)})
        query_duration_seconds.observe(time.monotonic() - start_time)
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

    # Extract chunk_ids for Block 18 (v0.3) — list of UUIDs from this retrieval
    chunk_ids = [c["chunk_id"] for c in ranked_chunks if "chunk_id" in c]

    # Accumulate retrieval chunks counter (D-122 Phase 2)
    if ranked_chunks:
        retrieval_chunks_returned_total.inc(len(ranked_chunks))

    # 5. Retrieve conversation history from event payload
    conversation_history = event.get("conversation_history", [])

    # 6. Spend cap gate — D-125, D-006
    # Check before assembling context and calling LLM.
    # Cap = pre-authorised daily limit set by owner; no confirmation dialog needed.
    daily_cap = get_daily_cap()
    if daily_cap is not None:
        today_spend = await get_today_spend_usd()
        if today_spend >= daily_cap:
            log.warning(
                "spend_cap_reached",
                today_spend_usd=today_spend,
                cap_usd=daily_cap,
            )
            llm_cost_cap_exceeded_total.inc()

            # Emit cost.cap_exceeded to Block 13 — routes to owner notification (D-003)
            await _emit_event(
                "cost.cap_exceeded",
                {
                    "event_id": str(event_id),
                    "conversation_id": str(conversation_id),
                    "today_spend_usd": today_spend,
                    "cap_usd": daily_cap,
                },
            )

            # Canned response — no LLM call made
            canned = (
                "Daily spend cap reached. "
                "I won't make further LLM calls today. "
                "The cap resets at midnight UTC."
            )
            response_payload = {
                "event_id": str(event_id),
                "response_text": canned,
                "confidence": {
                    "chunks_returned": len(ranked_chunks),
                    "highest_relevance_score": confidence["highest_relevance_score"],
                    "threshold_met": False,
                },
                "chunk_ids": chunk_ids,
            }
            cache.set(conversation_id, event_id, response_payload)
            await _emit_event(
                _EVENT_QUERY_RESPONSE,
                {**response_payload, "conversation_id": str(conversation_id)},
            )
            query_duration_seconds.observe(time.monotonic() - start_time)
            return

    # 7. Semantic memory retrieval — v0.7, D-128, AC-3
    # Embed the query and search clive_state.memory_entities by cosine similarity.
    # Non-fatal: any failure produces [] and query continues without memory.
    memory_entities_retrieved: list[dict[str, Any]] = []
    try:
        query_embedding = await llm.embed(user_input)
        memory_entities_retrieved = await memory.retrieve_entities(
            query_embedding, top_k=5
        )
        if memory_entities_retrieved:
            log.info(
                "memory_entities_retrieved",
                count=len(memory_entities_retrieved),
            )
    except Exception as exc:
        log.warning("memory_retrieval_skipped", error=str(exc))

    # 8. Assemble context (D-044) — memory entities injected as Tier 3.5 (D-128)
    assembled = ctx.assemble(
        personality=personality_doc,
        alignment_rules=alignment_doc,
        conversation_history=conversation_history,
        retrieved_chunks=ranked_chunks,
        memory_entities=memory_entities_retrieved,
    )

    # 9. Call LLM (D-077) — returns (text, usage_data) since v0.6
    response_text, usage_data = await llm.complete(
        personality=assembled.personality,
        alignment_rules=assembled.alignment_rules,
        conversation_history=assembled.conversation_history,
        retrieved_chunks=assembled.retrieved_chunks,
        user_query=user_input,
        memory_entities=assembled.memory_entities,
    )

    # 10. Record usage to clive_state.llm_usage (D-125)
    cost_usd = compute_cost(
        usage_data["model"],
        usage_data["prompt_tokens"],
        usage_data["completion_tokens"],
    )
    await record_usage(
        usage_data["model"],
        usage_data["prompt_tokens"],
        usage_data["completion_tokens"],
        cost_usd,
    )

    # Prometheus cost metrics (D-125, D-122)
    model_label = usage_data["model"]
    llm_tokens_total.labels(model=model_label, type="prompt").inc(usage_data["prompt_tokens"])
    llm_tokens_total.labels(model=model_label, type="completion").inc(usage_data["completion_tokens"])
    llm_cost_usd_total.labels(model=model_label).inc(cost_usd)

    # 11. Build response and cache it
    # chunk_ids included so Block 18 can tag specific chunks as poor quality
    response_payload = {
        "event_id": str(event_id),
        "response_text": response_text,
        "confidence": confidence,
        "chunk_ids": chunk_ids,
    }
    cache.set(conversation_id, event_id, response_payload)

    # 12. Emit query.response
    await _emit_event(
        _EVENT_QUERY_RESPONSE,
        {**response_payload, "conversation_id": str(conversation_id)},
    )

    # Record query duration (D-122 Phase 2)
    query_duration_seconds.observe(time.monotonic() - start_time)

    log.info(
        "query_handled",
        event_id=str(event_id),
        chunks_used=len(assembled.retrieved_chunks),
        memory_entities_used=len(assembled.memory_entities),
        threshold_met=confidence["threshold_met"],
        cost_usd=cost_usd,
        model=model_label,
    )

    # 13. Post-response memory operations — v0.7, D-128
    # These run after query.response has been emitted. Non-fatal throughout.
    # a. Extract entities from the completed turn.
    # b. Store entities with embeddings in clive_state.memory_entities.
    # c. Consolidate old turns if threshold triggered.
    try:
        entities = await llm.extract_entities(user_input, response_text)
        if entities:
            entity_values = [e["value"] for e in entities]
            embeddings = await llm.embed_batch(entity_values)
            await memory.store_entities(
                entities,
                source_turn_id=None,   # turn_id not available here; orchestrator owns turn writes
                embeddings=embeddings,
            )
        await memory.consolidate_if_needed(conversation_id, llm.summarise_turns)
    except Exception as exc:
        # Any failure in memory operations is non-fatal.
        # The response has already been delivered.
        log.warning("post_response_memory_failed", error=str(exc))
