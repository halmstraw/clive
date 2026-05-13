---
id: D-028
title: Queue overflow rejects new events at source; owner notified; no silent drops
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 4 (Interface/Egress),
        Block 25 (Observability), all emitting blocks
agents: Systems Agent, Experience Agent (Block 4),
        Infrastructure Agent (Block 25)
---

## Context
When Block 13 is unavailable, emitting blocks accumulate events in local
queues. When those queues fill, the system must choose between dropping
events or rejecting new work. Silently dropping events would deceive the
owner about what CLIVE received and processed.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
When a block's local event queue reaches capacity during orchestrator
unavailability, new events are rejected at the source. The block stops
accepting new work until the queue drains. The owner is informed via
Block 4 that CLIVE is at capacity. No events are dropped silently.

## Rationale
Silent event loss violates the alignment principle that CLIVE does not
act deceptively. Visible backpressure is honest; silent dropping is not.

## Consequences
Rules out dropping oldest queued events to make room for new ones. Rules
out silent event drops of any kind. Rules out queue overflow behaviour
that discards events without owner notification.

## Related Decisions
D-003 (event bus principle), D-025 (at-least-once delivery),
D-031 (retry with exponential backoff).
