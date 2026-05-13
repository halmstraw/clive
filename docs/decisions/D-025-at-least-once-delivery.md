---
id: D-025
title: Block 13 provides at-least-once event delivery; all subscribers must be idempotent
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 9 (Action Layer), Block 16 (Storage),
        all subscriber blocks
agents: Systems Agent, Intelligence Agent, Knowledge Agent — all agents
        owning subscriber blocks
---

## Context
Exactly-once delivery is expensive to guarantee in a distributed system.
At-least-once is simpler and sufficient if all consumers are idempotent.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Central Orchestrator provides at-least-once event delivery. All
subscriber blocks must be idempotent.

Note: Block 9 (Action Layer) must treat duplicate confirmation events as
already-handled, not as new requests.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out exactly-once delivery guarantees in v1. Rules out any block
assuming it receives each event precisely once. Each block design must
account for duplicate delivery.

## Related Decisions
D-003 (event bus principle), D-026 (per-conversation ordering),
D-031 (retry parameters), D-046 (Block 8 duplicate query cache).
