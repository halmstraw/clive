---
id: D-045
title: Block 8 acknowledges unavailable action intent and emits structured event
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 13 (Orchestrator), Block 25 (Observability)
agents: Intelligence Agent, Systems Agent
---

## Context
At v0.1, CLIVE is query-only (D-035). When a user implies an action, Block 8
must respond honestly rather than silently ignoring the intent.

## Options Considered
A. Silently ignore action intent — violates alignment constitution (deceptive).
B. Acknowledge intent, state unavailability, emit structured event (chosen)
   — honest and creates useful signal for future prioritisation.
C. Attempt to execute action — ruled out at v0.1.

## Decision
When Block 8 receives a query implying an action it cannot perform at v0.1,
it acknowledges the intent, states clearly that actions are not yet available,
offers what it can do, and emits a structured event
(action.requested_unavailable) via the event bus. Personality governs tone.

## Rationale
The alignment constitution requires CLIVE not to act deceptively — silently
ignoring action intent violates that. The structured event creates a real
signal about what capabilities the owner needs.

## Consequences
Rules out silently ignoring action intent. Rules out attempting to execute
actions at v0.1. Rules out acknowledging without logging the signal.

## Related Decisions
D-006 (confirmation gate), D-035 (v0.1 query-only scope).
