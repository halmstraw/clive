---
id: D-046
title: Block 8 caches response by event ID per conversation; returns cached on duplicate
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 13 (Orchestrator)
agents: Intelligence Agent, Systems Agent
---

## Context
Under at-least-once delivery (D-025), Block 8 may receive the same query
event twice. It must respond idempotently without silently discarding events
or reprocessing unnecessarily.

## Options Considered
A. Silent discard on duplicate — leaves user with no answer if first delivery
   failed; violates honesty.
B. Cache response keyed by event ID for conversation duration (chosen) —
   harmless under at-least-once; user always gets an answer.
C. Reprocess duplicate as a new query — wastes resources and may produce
   inconsistent responses.

## Decision
Block 8 handles duplicate query events by caching its response keyed by
event ID for the duration of the conversation. On duplicate receipt, it
returns the cached response without reprocessing.

## Rationale
Block 8 cannot know whether its first response was successfully delivered.
Re-emitting the cached response is harmless under at-least-once semantics.
Cache lifetime is bounded to conversation scope at v0.1.

## Consequences
Rules out silent discard of duplicate events. Rules out reprocessing
duplicates as new queries. Rules out unbounded idempotency caches.

## Related Decisions
D-025 (at-least-once delivery), D-003 (event bus principle).
