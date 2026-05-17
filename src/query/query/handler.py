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

v0.8: Block 17 Tool Registry integration (D-137, D-138).
  - Live tool registry fetched at the start of each query (TTL-cached, 60s).
  - Available tools injected into the LLM system prompt (name + description only;
    permission_scope is never exposed to the LLM).
  - Action intent detection unchanged (ACTION_VERBS heuristic).
  - Action validation: detected verb matched against live registry via
    _find_tool_in_registry(). Two outcomes:
      * Tool found in registry → emit action.requested for Block 9 to handle.
      * Tool not in registry / registry empty → no event emitted; respond with
        "That capability is not currently available." (D-138 requirement).
  - This is Block 8's own gate. Block 13 also validates independently (D-138).

v0.9: Block 16 retrieval tracking (D-140).
  - After each fresh query that returns non-empty chunk_ids: increment
    retrieval_count and update last_retrieved_at on the returned chunks.
  - Non-fatal: any DB failure is caught and logged as WARN; query unaffected.
  - Skipped on cache hits (D-046) — only fresh retrievals are tracked.
  - Enables knowledge_maintenance worker (Wave 3-B) to identify stale chunks.

v0.12: Block 29 self-knowledge queries + Block 20 config-aware spend cap (D-149).
  - Step 2.5: self-knowledge intent detection runs after tool registry fetch.
    Matched queries short-circuit vector RAG and return live state directly.
  - get_daily_cap() is now async — reads clive_state.config before env var.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

import httpx
import structlog

from . import context as ctx
from . import llm
from . import memory
from .db import get_pool
from .idempotency import cache
from .metrics import (
    llm_cost_cap_exceeded_total,
    llm_cost_usd_total,
    llm_tokens_total,
    queries_total,
    query_duration_seconds,
    retrieval_chunks_returned_total,
)
from .registry import ToolDescriptor, registry
from .spend import compute_cost, get_daily_cap, get_today_spend_usd, record_usage

log = structlog.get_logger()

# Action-intent keywords — simple heuristic for linguistic detection.
# These trigger the action validation path; they do NOT define what is available.
# Tool availability is determined exclusively by the live registry (D-138).
# Evolves post-v0.1 via Block 21.
ACTION_VERBS = {
    "send", "email", "message", "book", "schedule", "create",
    "delete", "update", "post", "call", "order", "buy", "pay",
    "remind", "set", "add", "remove", "cancel", "upload",
}

# Self-knowledge phrase sets — intentionally broad.
# False positives are acceptable here; the user typing these is almost
# certainly asking about CLIVE's state, not issuing a regular query.
_SK_PHRASES: dict[str, list[str]] = {
    "documents": [
        "what documents do you know about",
        "what's in your knowledge base",
        "what is in your knowledge base",
        "list your documents",
        "what have you ingested",
        "what files do you have",
        "what documents have you",
        "show me your documents",
        "list documents",
    ],
    "tools": [
        "what tools do you have",
        "what can you do",
        "what are your capabilities",
        "what actions are available",
        "what capabilities do you have",
        "list your tools",
        "what tools are available",
        "show me your tools",
    ],
    "actions": [
        "what actions did you take",
        "what did you do",
        "recent actions",
        "action history",
        "what have you done this week",
        "what have you done recently",
        "show me recent actions",
        "list recent actions",
    ],
    "workers": [
        "what workers do you have",
        "what background tasks",
        "what runs on a schedule",
        "scheduled tasks",
        "what workers are running",
        "list your workers",
        "what background workers",
    ],
    "health": [
        "how much have you cost",
        "what's your status",
        "what is your status",
        "system health",
        "how much did you spend",
        "are you healthy",
        "what's your daily cap",
        "what is your daily cap",
        "how much have you spent",
        "show me your status",
        "system status",
    ],
}

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")  # NOSONAR — Docker-internal, no TLS
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
    """Heuristic: detect if query implies an action request.

    Returns the first detected action verb, or None.
    Detection is intentionally broad — validation against the live registry
    (via _find_tool_in_registry) determines whether the action is actually
    executable.
    """
    words = text.lower().split()
    for word in words:
        if word in ACTION_VERBS:
            return word
    return None


def _detect_self_knowledge_intent(text: str) -> str | None:
    """Detect if the query is asking about CLIVE's own state or capabilities.

    Returns one of 'documents', 'tools', 'actions', 'workers', 'health',
    or None if no self-knowledge phrase matches.

    Matching is case-insensitive substring search. Intentionally broad —
    false positives are better than misses for this intent class.
    """
    normalised = text.lower()
    for intent, phrases in _SK_PHRASES.items():
        for phrase in phrases:
            if phrase in normalised:
                return intent
    return None


# Regex for conversational spend cap detection.
# Matches "set (my )?(daily )?(spend )?(cap|limit|budget) to $X" or "cap to $X.XX".
_SPEND_CAP_RE = re.compile(
    r"set\s+(?:my\s+)?(?:daily\s+)?(?:spend\s+)?(?:cap|limit|budget)\s+to\s+\$?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _detect_spend_cap_intent(text: str) -> str | None:
    """Return the new cap value as a string if the query sets the daily spend cap.

    Returns the parsed dollar value (e.g. "5.0") or None.
    Only matches explicit set-cap phrases — self-knowledge phrases like "what's
    my cap" are handled by the 'health' self-knowledge intent instead.
    """
    m = _SPEND_CAP_RE.search(text)
    return str(float(m.group(1))) if m else None


def _find_tool_in_registry(
    verb: str,
    tools: list[ToolDescriptor],
) -> ToolDescriptor | None:
    """Find the first registry tool that relates to the detected action verb.

    Matches by tokenising tool_name (underscore-split) and display_name
    (space-split) into a word set, then checking if:
      - the verb exactly equals any word, OR
      - any word starts with the verb (minimum 3-char verb to avoid noise)

    This allows "remind" to match "reminder", "search" to match "web_search",
    and "delete" to match "delete_document" without hardcoding any tool names.
    Tool names are sourced exclusively from the live registry.

    Args:
        verb:  detected action verb (lowercase), e.g. "remind", "search"
        tools: snapshot of the live registry (enabled + non-deprecated only)

    Returns:
        First matching ToolDescriptor, or None if no tool matches.
    """
    v = verb.lower()
    if len(v) < 3:
        # Very short verbs (e.g. "do", "go") would match too broadly
        return None
    for tool in tools:
        # Build a word set from tool_name (underscore-split) and display_name
        words = set(tool.tool_name.split("_")) | set(tool.display_name.lower().split())
        for word in words:
            if word == v or word.startswith(v):
                return tool
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


async def _update_chunk_retrieval_stats(chunk_ids: list[str]) -> None:
    """Increment retrieval_count and update last_retrieved_at for accessed chunks.

    Called after each fresh query that returns non-empty chunk_ids (v0.9, D-140).
    Not called on cache hits (D-046). Action-intent early returns produce
    chunk_ids=[] so the early-exit guard covers that case automatically.

    Non-fatal: any DB failure is caught and logged as WARN. Query success
    is unaffected regardless of tracking outcome.

    D-043: direct DB write within Block 8's own execution context —
    same pattern as memory entity storage (v0.7).
    """
    if not chunk_ids:
        return
    try:
        pool = get_pool()
        await pool.execute(
            """
            UPDATE clive_search.chunks
            SET retrieval_count = retrieval_count + 1,
                last_retrieved_at = NOW()
            WHERE chunk_id = ANY($1::uuid[])
            """,
            chunk_ids,
        )
        log.debug("chunk_retrieval_tracked", chunk_count=len(chunk_ids))
    except Exception as exc:
        log.warning(
            "chunk_retrieval_tracking_failed",
            chunk_count=len(chunk_ids),
            error=str(exc),
        )


async def _handle_self_knowledge_query(
    intent: str,
    zone_scope: str,
    event_id: uuid.UUID,
    source_surface: str,
    available_tools: list[ToolDescriptor],
) -> dict[str, Any]:
    """Fetch and format a self-knowledge response for the given intent.

    Each intent hits a dedicated orchestrator endpoint that returns live state.
    All HTTP calls use a 10s timeout. Failures are non-fatal — any exception
    produces a graceful fallback response rather than propagating to the caller.

    Returns a response_payload dict with the same shape as other early-return
    paths in handle_query().
    """
    _empty_confidence = {
        "chunks_returned": 0,
        "highest_relevance_score": 0.0,
        "threshold_met": False,
    }

    def _build_payload(text: str) -> dict[str, Any]:
        return {
            "event_id": str(event_id),
            "response_text": text,
            "confidence": _empty_confidence,
            "chunk_ids": [],
            "source_surface": source_surface,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if intent == "documents":
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/retrieve/document-list",
                    json={"zone_scope": zone_scope},
                )
                resp.raise_for_status()
                data = resp.json()
                docs = data.get("documents", [])
                if not docs:
                    text = "My knowledge base is empty."
                else:
                    lines = [f"I have {len(docs)} document(s) in my knowledge base:"]
                    for i, d in enumerate(docs, 1):
                        date_part = d.get("ingested_at", "")[:10] if d.get("ingested_at") else ""
                        chunks_part = f"{d.get('chunk_count', 0)} chunks"
                        name = d.get("filename", d.get("title", "unknown"))
                        line = f"{i}. {name} — {chunks_part}"
                        if date_part:
                            line += f" ({date_part})"
                        lines.append(line)
                    text = "\n".join(lines)

            elif intent == "tools":
                if not available_tools:
                    text = "No tools are currently registered."
                else:
                    lines = [f"I have {len(available_tools)} tool(s) available:"]
                    for t in available_tools:
                        lines.append(f"- {t.display_name}: {t.description}")
                    text = "\n".join(lines)

            elif intent == "actions":
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/retrieve/action-history",
                    json={"zone_scope": zone_scope, "days": 7},
                )
                resp.raise_for_status()
                data = resp.json()
                actions = data.get("actions", [])
                if not actions:
                    text = "No actions recorded in the last 7 days."
                else:
                    lines = [f"In the last 7 days I took {len(actions)} action(s):"]
                    for a in actions:
                        date_part = a.get("executed_at", "")[:10] if a.get("executed_at") else ""
                        status = a.get("status", "unknown")
                        action_type = a.get("action_type", "unknown")
                        target = a.get("action_target", "")
                        line = f"- {action_type}"
                        if target:
                            line += f" on {target}"
                        line += f" — {status}"
                        if date_part:
                            line += f" ({date_part})"
                        lines.append(line)
                    text = "\n".join(lines)

            elif intent == "workers":
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/retrieve/workers",
                    json={},
                )
                resp.raise_for_status()
                data = resp.json()
                workers = data.get("workers", [])
                if not workers:
                    text = "No workers are registered."
                else:
                    lines = [f"I have {len(workers)} background worker(s):"]
                    for w in workers:
                        enabled = "yes" if w.get("enabled") else "no"
                        schedule = w.get("schedule", "unscheduled")
                        name = w.get("display_name", w.get("worker_name", "unknown"))
                        description = w.get("description", "")
                        line = f"- {name}"
                        if description:
                            line += f": {description}"
                        line += f", schedule: {schedule}, enabled: {enabled}"
                        lines.append(line)
                    text = "\n".join(lines)

            elif intent == "health":
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/retrieve/status",
                    json={"zone_scope": zone_scope},
                )
                resp.raise_for_status()
                data = resp.json()
                doc_count = data.get("doc_count", 0)
                chunk_count = data.get("chunk_count", 0)
                spend_today = data.get("llm_spend_today_usd", 0.0)
                cap_raw = data.get("daily_cap_usd")
                cap_str = f"${cap_raw:.2f}" if cap_raw is not None else "not set"
                last_query = (data.get("last_query_at") or "")[:10] or "never"
                last_ingest_file = data.get("last_doc_name", "")
                last_ingest_date = (data.get("last_doc_at") or "")[:10]
                last_ingest = f"{last_ingest_file} ({last_ingest_date})" if last_ingest_file else "never"
                text = (
                    f"System status:\n"
                    f"- Documents: {doc_count} ({chunk_count} chunks)\n"
                    f"- LLM spend today: ${spend_today:.4f}\n"
                    f"- Daily cap: {cap_str}\n"
                    f"- Last query: {last_query}\n"
                    f"- Last ingest: {last_ingest}"
                )

            else:
                text = "Could not retrieve that information right now."

    except Exception as exc:
        log.warning("self_knowledge_query_failed", intent=intent, error=str(exc))
        text = "Could not retrieve that information right now."

    return _build_payload(text)


async def handle_query(event: dict[str, Any]) -> None:
    """Handle a query.received event.

    Steps:
    1.   Idempotency check (D-046)
    2.   Fetch live tool registry (v0.8, D-137) — TTL-cached, 60s
    2.5. Self-knowledge detection (v0.12, D-149) — short-circuits RAG
    3.   Action intent detection and registry validation (D-045, D-138)
    4.   Retrieve system documents via orchestrator (D-043, D-048)
    5.   Retrieve knowledge chunks via orchestrator (D-043)
    6.   Retrieve conversation history from event payload
    7.   Spend cap check — return canned response if exceeded (D-125)
    8.   Semantic memory retrieval (v0.7, D-128, AC-3)
    9.   Assemble context (D-044) — includes memory entities as Tier 3.5
    10.  Call LLM with live tool list in system prompt (D-077, v0.8 D-137)
    11.  Record LLM usage to clive_state.llm_usage (D-125)
    12.  Build response payload, cache, emit query.response (v0.3: include chunk_ids)
    13.  Record query duration (D-122 Phase 2)
    14.  Retrieval tracking (v0.9, D-140) — non-fatal:
         Update retrieval_count + last_retrieved_at on returned chunks.
         Skipped if chunk_ids is empty. Not called on cache hits (D-046).
    15.  Post-response memory operations (v0.7, D-128) — non-fatal:
         a. Extract entities from the turn (AC-2)
         b. Store entities with embeddings (AC-2)
         c. Consolidate old turns if threshold met (AC-5)
    """
    start_time = time.monotonic()

    event_id = uuid.UUID(event["event_id"])
    conversation_id = uuid.UUID(event["conversation_id"])
    user_input = event["input_text"]
    zone_scope = event.get("zone_scope", "personal")
    source_surface = event.get("source_surface", "telegram")  # D-146: route response to origin surface

    # Increment query counter (D-122 Phase 2)
    queries_total.inc()

    # 1. Idempotency check — D-046
    cached = cache.get(conversation_id, event_id)
    if cached:
        log.info("idempotency_cache_hit", event_id=str(event_id))
        await _emit_event(_EVENT_QUERY_RESPONSE, {**cached, "conversation_id": str(conversation_id)})
        query_duration_seconds.observe(time.monotonic() - start_time)
        return

    # 2. Fetch live tool registry — v0.8 (D-137)
    # TTL-cached (60s). On DB failure, returns stale or empty cache gracefully.
    # Used for: (a) action intent validation, (b) system prompt injection.
    available_tools = await registry.get_tools()

    # 2.5. Self-knowledge detection — v0.12 (D-149)
    # Runs after tool registry fetch so available_tools is in scope.
    # Runs before action intent so "what tools can you delete?" hits self-knowledge.
    self_knowledge_intent = _detect_self_knowledge_intent(user_input)
    if self_knowledge_intent:
        sk_payload = await _handle_self_knowledge_query(
            self_knowledge_intent, zone_scope, event_id,
            source_surface, available_tools,
        )
        cache.set(conversation_id, event_id, sk_payload)
        await _emit_event(
            _EVENT_QUERY_RESPONSE,
            {**sk_payload, "conversation_id": str(conversation_id)},
        )
        query_duration_seconds.observe(time.monotonic() - start_time)
        return

    # 2.6. Config intent detection — v0.12 (D-149)
    # Conversational config changes route through Block 9 confirmation gate (D-006).
    # Spend cap is the only config type supported here; worker.reschedule requires
    # explicit cron syntax and is handled by Block 23 commands instead.
    new_cap = _detect_spend_cap_intent(user_input)
    if new_cap is not None:
        cap_event_id = uuid.uuid4()
        await _emit_event(
            "action.pending",
            {
                "event_id": str(cap_event_id),
                "conversation_id": str(conversation_id),
                "zone_scope": zone_scope,
                "payload": {
                    "action_type": "config.set_spend_cap",
                    "action_target": new_cap,
                    "action_description": f"Set daily spend cap to ${float(new_cap):.2f}.",
                    "source_surface": source_surface,
                },
            },
        )
        cap_response = {
            "event_id": str(event_id),
            "response_text": (
                f"I'll set the daily spend cap to ${float(new_cap):.2f}. "
                "I'll confirm before making the change."
            ),
            "confidence": {"chunks_returned": 0, "highest_relevance_score": 0.0, "threshold_met": False},
            "chunk_ids": [],
            "source_surface": source_surface,
        }
        cache.set(conversation_id, event_id, cap_response)
        await _emit_event(_EVENT_QUERY_RESPONSE, {**cap_response, "conversation_id": str(conversation_id)})
        query_duration_seconds.observe(time.monotonic() - start_time)
        return

    # 3. Action intent detection and registry validation — D-045, D-138
    # ACTION_VERBS heuristic detects that the user is requesting an action.
    # _find_tool_in_registry then validates whether any live tool handles it.
    # Block 8's own gate — Block 13 also validates independently (D-138).
    action_verb = _detect_action_intent(user_input)
    if action_verb:
        matched_tool = _find_tool_in_registry(action_verb, available_tools)

        if matched_tool:
            # Tool is registered and enabled — route to Block 9 via Block 13.
            # Block 9's confirmation gate (D-006) applies; Block 8 acknowledges.
            log.info(
                "action_intent_routed",
                verb=action_verb,
                tool=matched_tool.tool_name,
            )
            await _emit_event(
                "action.requested",
                {
                    "conversation_id": str(conversation_id),
                    "event_id": str(event_id),
                    "tool_name": matched_tool.tool_name,
                    "original_query_context": user_input,
                },
            )
            response_text = (
                f"I'll work on that using {matched_tool.display_name}. "
                "I'll confirm the details with you before proceeding."
            )
        else:
            # Tool not in registry / registry empty — Block 8's gate.
            # Do NOT emit an action event (D-138 requirement).
            log.info(
                "action_intent_blocked",
                verb=action_verb,
                reason="not_in_registry",
                available_tool_count=len(available_tools),
            )
            response_text = "That capability is not currently available."

        response_payload = {
            "event_id": str(event_id),
            "response_text": response_text,
            "confidence": {
                "chunks_returned": 0,
                "highest_relevance_score": 0.0,
                "threshold_met": False,
            },
            "chunk_ids": [],
            "source_surface": source_surface,
        }
        cache.set(conversation_id, event_id, response_payload)
        await _emit_event(
            _EVENT_QUERY_RESPONSE,
            {**response_payload, "conversation_id": str(conversation_id)},
        )
        query_duration_seconds.observe(time.monotonic() - start_time)
        return

    # 4. Retrieve system documents via orchestrator (D-043, D-048)
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

    # 5. Retrieve knowledge chunks via orchestrator (D-043)
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

    # 6. Retrieve conversation history from event payload
    conversation_history = event.get("conversation_history", [])

    # 7. Spend cap gate — D-125, D-006
    # Check before assembling context and calling LLM.
    # Cap = pre-authorised daily limit set by owner; no confirmation dialog needed.
    # get_daily_cap() is async since v0.12 — reads config table before env var (D-149).
    daily_cap = await get_daily_cap()
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
                "source_surface": source_surface,
            }
            cache.set(conversation_id, event_id, response_payload)
            await _emit_event(
                _EVENT_QUERY_RESPONSE,
                {**response_payload, "conversation_id": str(conversation_id)},
            )
            query_duration_seconds.observe(time.monotonic() - start_time)
            # Retrieval tracking (v0.9, D-140) — chunks were fetched before cap check
            await _update_chunk_retrieval_stats(chunk_ids)
            return

    # 8. Semantic memory retrieval — v0.7, D-128, AC-3
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

    # 9. Assemble context (D-044) — memory entities injected as Tier 3.5 (D-128)
    assembled = ctx.assemble(
        personality=personality_doc,
        alignment_rules=alignment_doc,
        conversation_history=conversation_history,
        retrieved_chunks=ranked_chunks,
        memory_entities=memory_entities_retrieved,
    )

    # 10. Call LLM (D-077, v0.8 D-137)
    # available_tools passed so the system prompt includes the live tool list.
    # Returns (text, usage_data) since v0.6.
    response_text, usage_data = await llm.complete(
        personality=assembled.personality,
        alignment_rules=assembled.alignment_rules,
        conversation_history=assembled.conversation_history,
        retrieved_chunks=assembled.retrieved_chunks,
        user_query=user_input,
        memory_entities=assembled.memory_entities,
        available_tools=available_tools,
    )

    # 11. Record usage to clive_state.llm_usage (D-125)
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

    # 12. Build response and cache it
    # chunk_ids included so Block 18 can tag specific chunks as poor quality
    response_payload = {
        "event_id": str(event_id),
        "response_text": response_text,
        "confidence": confidence,
        "chunk_ids": chunk_ids,
        "source_surface": source_surface,  # D-146: Block 4 routes response to origin surface
    }
    cache.set(conversation_id, event_id, response_payload)

    # Emit query.response
    await _emit_event(
        _EVENT_QUERY_RESPONSE,
        {**response_payload, "conversation_id": str(conversation_id)},
    )

    # 13. Record query duration (D-122 Phase 2)
    query_duration_seconds.observe(time.monotonic() - start_time)

    log.info(
        "query_handled",
        event_id=str(event_id),
        chunks_used=len(assembled.retrieved_chunks),
        memory_entities_used=len(assembled.memory_entities),
        threshold_met=confidence["threshold_met"],
        cost_usd=cost_usd,
        model=model_label,
        available_tools=len(available_tools),
    )

    # 14. Retrieval tracking (v0.9, D-140) — non-fatal, skip if no chunks returned
    await _update_chunk_retrieval_stats(chunk_ids)

    # 15. Post-response memory operations — v0.7, D-128
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
