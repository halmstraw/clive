---
id: D-043
title: Block 8 retrieval from Block 16 is orchestrator-mediated; not a full event round-trip
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 13 (Orchestrator), Block 16 (Storage)
agents: Intelligence Agent (Block 8), Systems Agent (Block 13),
        Knowledge Agent (Block 16)
---

## Context
Block 8 needs to retrieve chunks from Block 16 as part of every query.
A full event bus round-trip (retrieval.request / retrieval.result) satisfies
D-003 but adds latency and complexity. An alternative sanctioned pattern
is needed.

## Options Considered
A. Full event bus round-trip — D-003 compliant but adds unnecessary latency
   at v0.1 where retrieval has exactly one consumer.
B. Orchestrator-mediated synchronous sub-call (chosen) — Block 13 brokers
   the call; D-003 satisfied; call is logged and observable.
C. Direct Block 8 → Block 16 call — D-003 violation; ruled out.

## Decision
Block 8 retrieval from Block 16 is implemented as an orchestrator-mediated
synchronous call, not a full event bus round-trip. Block 13 brokers the
retrieval on Block 8's behalf as a sub-step within the query event lifecycle.
The call is logged and observable but does not produce separate bus events.

## Rationale
At v0.1, retrieval is always part of query processing — there is no
independent retrieval consumer. A full event bus round-trip adds latency
and complexity with no alignment or observability benefit, since Block 13
still mediates and logs the call. D-003 is satisfied because Block 13 is
always in the middle.

## Consequences
Rules out Block 8 calling Block 16 directly (D-003 violation). Rules out
full event bus round-trip for retrieval at v0.1.

## Related Decisions
D-003 (event bus principle), D-025 (at-least-once delivery),
D-044 (context allocation), D-046 (duplicate query cache).
