---
id: D-026
title: Block 13 guarantees per-conversation event ordering only; not global
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 9 (Action Layer),
        Block 10 (Workers), Block 11 (Memory)
agents: Systems Agent, Intelligence Agent
---

## Context
Global event ordering would serialise all processing across unrelated
conversations. Per-entity ordering adds complexity without clear benefit
at v0.1 query volume.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Central Orchestrator (Block 13) guarantees per-conversation event
ordering only. Events within a single conversation thread are delivered
in order. Events across unrelated threads may arrive out of order.

## Rationale
For a single-owner personal system, the natural ordering boundary is the
conversation. Multi-step sequences in CLIVE — query to action to
confirmation — occur within a thread, not across unrelated threads. Global
ordering serialises processing unnecessarily; per-entity ordering adds
complexity before there is evidence it is needed.

## Consequences
Rules out global event ordering in v1. Rules out per-entity ordering in
v1. Cross-conversation ordering is the caller's responsibility.

## Related Decisions
D-003 (event bus principle), D-025 (at-least-once delivery),
D-023 (single orchestrator instance).
