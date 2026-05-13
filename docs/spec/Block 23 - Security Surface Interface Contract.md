*Access & Security Agent requirements artefact — produced May 2026. Complete for v0.1. Held pending further direction on Blocks 6, 7, and 24.*

---
# Block 23 — Security (Surface): v0.1 Interface Contract

**Produced by:** Access & Security Agent
**Date:** May 2026
**Scope:** v0.1 only
**Status:** Complete for v0.1. Held pending further direction on Blocks 6, 7, and 24.

---

## Summary

Block 23 is the inbound surface — the single point through which the owner communicates with CLIVE at v0.1. It authenticates the owner, initiates or continues conversation sessions, emits input events to Block 13, and renders responses delivered back from Block 13.

This artefact declares the interface contract that any compliant surface implementation must satisfy. It does not name the surface (D-002, D-035 defer that choice). It makes the surface choice decidable.

---

## Governing Decisions

| Decision | Constraint on Block 23 |
|---|---|
| D-001 | Single owner — authentication is identity verification for one person, not user selection |
| D-002 | No technology choices — contract declared, channel not named |
| D-003 | Event bus — Block 23 emits to Block 13 only; no direct calls to Block 8 or Block 16 |
| D-018 | Stateless — no session state held inside Block 23; all state in event payloads or Block 16 |
| D-025 | At-least-once delivery — Block 23 must be idempotent on duplicate response events |
| D-035 | Query-only at v0.1 — no action submission, no worker invocation |
| D-050 | Single zone "personal" hard-coded — Block 23 carries zone scope in every emitted event |
| D-057 | Channel-as-authentication at v0.1 — the surface channel is the authentication factor |

---

## What Block 23 Is

At v0.1, Block 23 is the inbound surface only. It is not a service with its own intelligence. It does not decide how to respond. It receives text input, emits a structured event, and renders a structured response. The boundary between Block 23 (inbound) and Block 4 (outbound channel, owned by Experience Agent) is: Block 23 owns everything from owner input to event emission. Block 4 owns everything from response event receipt to display rendering. At v0.1 these may be the same physical channel — the logical boundary is what matters for contract purposes.

---

## Compliant Surface Requirements

### What it must do

- Accept text input from the owner
- Authenticate the owner via channel membership (D-057) — no additional credential required
- Generate or recover a `conversation_id` for session continuity — this ID is carried in event payloads, not held in Block 23 local state (D-018)
- Carry zone scope `"personal"` in every emitted event (D-050)
- Emit a `query.received` event to Block 13 on every owner input submission
- Render response text delivered via `query.response` events from Block 13
- Render confidence signals if present in the event payload (retrieval quality indicators per D-047)
- Render system notification events if delivered by Block 13 (capacity alerts per D-028, dead-letter notifications per D-031)
- Handle duplicate `query.response` events idempotently — render the first, discard subsequent duplicates for the same `event_id` (D-025)

### What it must not do

- Hold conversation state between events (D-018 violation)
- Call Block 8, Block 16, or any other block directly (D-003 violation)
- Submit or queue actions (D-035 — query-only at v0.1)
- Accept input from any identity other than the authenticated owner channel (D-057)
- Silently drop events or suppress system notifications (D-028)

---

## Event Schema

### Emits — `query.received`

Emitted to Block 13 on every owner input.

```json
{
  "event_type": "query.received",
  "event_id": "<uuid>",
  "conversation_id": "<uuid>",
  "zone_scope": "personal",
  "input_text": "<string>",
  "timestamp": "<ISO8601>",
  "surface_type": "<string>"
}
```

- `event_id` — unique per submission; used for idempotency downstream
- `conversation_id` — session identity; generated on first message, recovered on continuation
- `zone_scope` — hard-coded at v0.1 per D-050
- `surface_type` — surface identifier; declared at implementation time

### Consumes — `query.response`

Received from Block 13. Block 23 renders this to the owner.

```json
{
  "event_type": "query.response",
  "event_id": "<uuid>",
  "conversation_id": "<uuid>",
  "response_text": "<string>",
  "confidence": {
    "chunks_returned": "<int>",
    "highest_relevance_score": "<float>",
    "threshold_met": "<bool>"
  },
  "timestamp": "<ISO8601>"
}
```

- `event_id` — correlates to the originating `query.received` event_id

### Consumes — system notification events

Block 23 must render any system notification events routed by Block 13. These include at minimum:

- Capacity backpressure notifications (D-028)
- Dead-letter notifications after retry exhaustion (D-031)

The specific event types for these notifications are defined by Block 13's event taxonomy (owned by Systems Agent). Block 23 must render them faithfully without suppression.

---

## Authentication Model (D-057)

At v0.1, authentication is channel-as-authentication. The surface channel — whichever is chosen — is the authentication boundary. If the owner is in the channel, they are authenticated. No additional credential layer exists at v0.1.

**Threat model addressed:** Physical device or account compromise. CLIVE is not defended against someone who has full access to the owner's device and messaging account — that is outside the v0.1 scope.

**Threat model not addressed at v0.1:** Network-level impersonation; credential replay; session hijacking across surfaces. These are v0.2+ considerations conditional on the surface choice and sensitivity of data handled.

**Pre-condition on v0.2:** If CLIVE handles material sensitive to channel compromise before v0.2, the authentication model is revisited before that version ships. This is named in D-057.

---

## Session Identity

Block 23 generates a `conversation_id` on the first message of a new session. On subsequent messages in the same session, it recovers and carries the same `conversation_id`. The ID is carried in the event payload — it is not stored inside Block 23 (D-018). How Block 23 recovers the `conversation_id` across messages within a session (e.g. from the channel's thread model, from a lightweight session cookie, from a query to Block 16) is a surface-implementation detail, not a contract requirement. The contract requirement is: every event in the same conversation carries the same `conversation_id`.

---

## Zone Scope

At v0.1, every event Block 23 emits carries `zone_scope: "personal"`. This is hard-coded (D-050). Block 23 does not determine zone scope dynamically — it has one zone and always declares it. When the Access & Security Agent deepens Block 7 (full zone model), zone scope determination may become dynamic. That is a future contract extension, not a v0.1 concern.

---

## Boundary with Block 4 (Experience Agent)

Block 4 (Interface / Egress) is owned by the Experience Agent (not yet activated). The boundary:

- **Block 23 owns:** Inbound path — from owner input to `query.received` event emission. Authentication. Session initiation. Zone scope declaration.
- **Block 4 owns:** Outbound path — from `query.response` event receipt to rendered display. Formatting, personality expression in presentation, notification styling.

At v0.1, inbound and outbound may share the same physical channel (e.g. the same Telegram bot). The logical boundary stands regardless. This boundary must be confirmed with the Experience Agent when activated. It is flagged to the Architect for cross-block review.

---

## Open Items

| Item | Status | Owner |
|---|---|---|
| Surface choice (Telegram, CLI, native app, web) | Resolved — D-061. Surface is Telegram. | Closed |
| Block 4 boundary confirmation | Pending Experience Agent activation | Architect cross-block review |
| `conversation_id` recovery mechanism | Implementation detail | Surface implementation |
| System notification event types | Block 13 taxonomy | Systems Agent |
| v0.2 authentication review trigger | Pre-condition named in D-057 | Owner, conditional |

---

## Blocks 6, 7, 24 — Status

**Block 6 (Users):** Not on v0.1 critical path. Full user and agent identity model deferred. No requirements deepening begun.

**Block 7 (Trust Zones):** v0.1 dependency satisfied — single zone "personal" declared in D-050, carried by Block 23 per this contract. Full multi-zone model deferred. No requirements deepening begun.

**Block 24 (Sandboxing):** Paused. Supports Block 21 (Evolution Engine), which is paused at v0.1 (D-042). No requirements deepening begun.

---

*Access & Security Agent — session complete. Holding for further direction.*
*May 2026*
