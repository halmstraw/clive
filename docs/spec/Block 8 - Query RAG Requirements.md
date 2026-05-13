*Intelligence Agent requirements artefact — produced May 2026. Approved — Architect review complete May 2026.*

---
# Block 8 — Query / RAG: v0.1 Requirements

**Produced by:** Intelligence Agent
**Date:** May 2026
**Scope:** v0.1 only (D-035)
**Status:** Approved — Architect review complete May 2026

---

## Governing Decisions

The following active decisions directly constrain this artefact:

- **D-002** — No technology choices in requirements
- **D-003** — Event bus principle; all inter-block communication via Block 13
- **D-005** — Personality survives the Reaper
- **D-025** — At-least-once delivery; all blocks must be idempotent
- **D-026** — Per-conversation event ordering only
- **D-035** — v0.1 is query-only, single-surface; Blocks 1, 8, 13, 16, 22, 23 on critical path
- **D-037** — Alignment gate is rules-and-schema, not LLM-as-judge
- **D-039** — Personality encoded as versioned constitutional document plus system prompt content
- **D-043** — Retrieval is orchestrator-mediated synchronous call, not separate event pair
- **D-044** — Dynamic token budget allocation with priority ordering
- **D-045** — Action-intent queries: acknowledge, decline, emit `action.requested_unavailable`
- **D-046** — Idempotency via cached response keyed by event ID, conversation-scoped
- **D-047** — Confidence signal is retrieval quality metrics only

---

## v0.1 Scope Boundary

Block 8 at v0.1 is the reasoning core of a single-surface, query-only system. It receives a query, retrieves relevant knowledge, and returns a personality-consistent response.

Block 8 reads and responds. It does not write, send, schedule, or modify anything outside its own conversation state.

---

## What Block 8 Must Do

### 1. Receive query events from Block 13

Block 8 subscribes to `query.submitted` events on the event bus. It does not accept queries from any other source. Every query arrives as a structured event with conversation ID, user input, and metadata (surface context, user identity, timestamp, event ID).

### 2. Retrieve relevant knowledge from Block 16

Block 8 requests retrieval via an orchestrator-mediated synchronous call (D-043). Block 13 brokers the call to Block 16 as a sub-step within the `query.submitted` event lifecycle. The retrieval is logged and observable but is not a separate event pair.

Retrieval must respect trust zone boundaries — Block 8 never sees knowledge from a zone the requesting user is not permitted to access. At v0.1 this is likely a single zone (personal), but the interface must not assume a single zone.

### 3. Assemble context for LLM reasoning

Block 8 assembles the LLM context window using dynamic allocation with priority ordering (D-044):

- **Priority 1 — Personality document** (Block 1 via D-039). Always present. Never displaced.
- **Priority 2 — Alignment rules** (Block 22). Query-time behavioural constraints. Always present.
- **Priority 3 — Conversation history** (episodic memory, current session). Summarised or truncated under budget pressure, never silently dropped.
- **Priority 4 — Retrieved knowledge chunks** (Block 16). Ranked by relevance. Filled to remaining budget. If nothing relevant is retrieved, Block 8 proceeds without retrieval context and signals this in response metadata.

Tiers 1 and 2 take their full size first. Remaining budget is split dynamically between Tiers 3 and 4 with a declared minimum guarantee for each. Surplus flows to whichever tier has more content to contribute. Specific minimum guarantees are implementation details to be declared before build begins.

### 4. Synthesise a response

Block 8 calls the LLM with assembled context and the user's query. The response must be consistent with the personality document. Block 8 does not add its own tone or style — personality is defined by the document loaded at Priority 1.

### 5. Express uncertainty rather than confabulate

When Block 8 has low confidence — insufficient retrieval results, ambiguous query, contradictory knowledge — it must say so. The personality document governs *how* uncertainty is expressed (D-039), but the requirement to express it is a Block 8 constraint, not a personality choice. Block 8 must never fabricate information to fill a gap.

### 6. Emit response events

Block 8 emits a `query.response` event to Block 13 containing: response text, retrieval quality metrics (D-047), conversation ID, event ID, and timestamp. Block 13 routes the response to the appropriate surface.

### 7. Maintain per-conversation episodic state

Within a single conversation, Block 8 tracks what has been said. This is the minimal v0.1 form of Block 11 (Memory Management). Episodic memory is conversation-scoped at v0.1 — it does not persist across conversations. It is used for context assembly (Priority 3) and multi-turn coherence.

### 8. Handle action-intent queries (D-045)

When a query implies an action Block 8 cannot perform ("send this to Sarah", "book a meeting"), Block 8 acknowledges the intent, declines clearly, and offers what it can do. Personality governs tone. Block 8 emits an `action.requested_unavailable` event carrying the recognised action type and conversation context.

### 9. Be idempotent (D-025, D-046)

Block 8 caches its response keyed by event ID for the duration of the conversation. On duplicate `query.submitted` receipt (same event ID), it returns the cached response without reprocessing. Cache lifetime is conversation-scoped.

---

## What Block 8 Must Not Do

1. **Take actions.** No writes, sends, deletes, creates, or modifications outside conversation state. Block 9 does not exist at v0.1.
2. **Bypass the event bus.** No direct calls to Block 16 or any other block. All communication via Block 13 (D-003). Retrieval uses the orchestrator-mediated pattern (D-043).
3. **Make technology assumptions.** No specific LLM, embedding model, or retrieval algorithm named (D-002).
4. **Persist knowledge across conversations.** No consolidation of episodic memory into long-term storage. No cross-conversation influence on retrieval or responses. Long-term memory is post-v0.1.
5. **Modify personality.** Block 8 consumes the personality document. It does not modify, override, or supplement it. Requests to change personality are declined per Block 22 and D-005.
6. **Self-improve.** No feedback loops, retrieval tuning, or prompt evolution. The Evolution Engine is not operational at v0.1 (D-035).
7. **Assess its own confidence via LLM self-rating.** Confidence signal is retrieval quality metrics only (D-047).

---

## Interface Requirements

### From Block 1 (Personality)

Block 8 requires:

- A retrieval interface: given the current personality version ID, return the personality document.
- A version identifier so Block 8 can detect personality changes mid-session.
- The document must be loadable into LLM context as Priority 1 without transformation.

Block 8 does not need to know how personality is authored or versioned — only how to retrieve and load it.

### From Block 13 (Orchestrator)

Block 8 requires the following event contract:

**Inbound:**
- `query.submitted` — conversation ID, user input (text), user identity, surface metadata, event ID, timestamp.

**Outbound:**
- `query.response` — conversation ID, response text, retrieval quality metrics (chunk count, highest relevance score, threshold met flag), event ID, timestamp.
- `action.requested_unavailable` — conversation ID, recognised action type, original query context, event ID, timestamp.

**Orchestrator-mediated sub-call (D-043):**
- Block 13 brokers a retrieval call to Block 16 on Block 8's behalf, passing: retrieval query, zone scope, result count limit, conversation ID.
- Block 16 returns: ranked chunks with source attribution, relevance scores, zone of origin.

Block 8 requires per-conversation ordering guarantee from Block 13 (D-026).

### From Block 16 (Storage)

Block 8 requires a retrieval contract (mediated by Block 13 per D-043):

- Accepts a query (text or structured) and returns ranked results.
- Supports zone-scoped retrieval — Block 8 passes permitted zone(s), Block 16 enforces the boundary.
- Returns chunks with source attribution and relevance scores.
- Returns an empty result set (not an error) when no relevant results exist.
- Is idempotent — same retrieval request returns consistent results within a reasonable window.

Block 8 does not need to know Block 16's storage technology, indexing strategy, or chunk structure.

### From Block 22 (Alignment)

Block 8 requires a query-time alignment rule set loadable into context (Priority 2). At v0.1 this governs:

- What Block 8 is permitted to say (no deceptive responses).
- How Block 8 handles action requests it cannot fulfil (acknowledge, do not fabricate capability).
- How Block 8 handles requests to modify personality or alignment (decline, route to owner awareness).
- Whether any query topics are restricted or require specific handling.

The alignment gate (D-037) operates at the event bus level via Block 13. Block 8 additionally needs alignment instructions in its context so responses are alignment-consistent at generation time, not only alignment-filtered after the fact.

---

## Event Schema Summary

| Event | Direction | Payload |
|---|---|---|
| `query.submitted` | Block 13 → Block 8 | conversation_id, user_input, user_identity, surface_metadata, event_id, timestamp |
| `query.response` | Block 8 → Block 13 | conversation_id, response_text, retrieval_metrics (chunk_count, max_relevance_score, threshold_met), event_id, timestamp |
| `action.requested_unavailable` | Block 8 → Block 13 | conversation_id, recognised_action_type, original_query_context, event_id, timestamp |

**Orchestrator-mediated retrieval sub-call (not a bus event):**

| Call | Direction | Payload |
|---|---|---|
| retrieval request | Block 13 → Block 16 (on behalf of Block 8) | retrieval_query, zone_scope, result_limit, conversation_id |
| retrieval result | Block 16 → Block 13 → Block 8 | ranked_chunks [{content, source_attribution, relevance_score, zone_of_origin}], result_count |

---

## Dependencies and Flags for Architect

1. **Block 16 retrieval contract** — The Knowledge Agent is designing Block 16 concurrently. The retrieval interface specified here (query in, ranked chunks out, zone-scoped, source-attributed) must be confirmed as compatible with Block 16's design. Cross-block coordination required.
2. **Block 22 query-time rule set** — The Architect owns Block 22. The requirement for a loadable alignment document at query time needs to be reflected in Block 22's design. What specific rules are in the v0.1 set is an Architect decision.
3. **Block 1 personality retrieval interface** — The Experience Agent (not yet activated) owns Block 1. Block 8 needs a retrieval mechanism for the personality document. Until the Experience Agent is active, the interface is declared here as a requirement and must be confirmed when Block 1 is designed.
4. **Minimum budget guarantees** — The specific minimum token guarantees for Tiers 3 and 4 (D-044) are implementation details, but they must be declared before Block 8 build begins. These may need to be informed by the actual size of the personality and alignment documents.

---

*Intelligence Agent — Block 8 v0.1 Requirements*
*May 2026*
