---
id: D-031
title: Block 13 retries with exponential backoff; dead-letter on exhaustion
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 25 (Observability), all subscriber blocks
agents: Systems Agent, Infrastructure Agent
---

## Context
When a subscriber block is temporarily unavailable, the orchestrator must
decide how aggressively to retry and what to do when retries are exhausted.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Block 13 retries unacknowledged event delivery a fixed number of times with
exponential backoff between attempts. After retry exhaustion, the event is
logged as undeliverable (dead-letter state) and the owner is notified via
Block 4.

## Rationale
Fixed retries with exponential backoff is simple, predictable, and
debuggable. Time-bounded retry is harder to reason about under load.
Subscriber-declared retry policies add configuration complexity before
there is evidence different blocks need different behaviour.

## Consequences
Rules out time-bounded retry windows. Rules out subscriber-declared retry
policies in v1. Rules out silent failure after exhausted retries. D-055
declares the specific parameters (5 retries, 2s initial backoff, ×2
multiplier).

## Related Decisions
D-025 (at-least-once delivery), D-055 (retry parameters),
D-028 (queue overflow backpressure).
