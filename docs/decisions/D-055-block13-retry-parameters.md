---
id: D-055
title: Block 13 retry parameters — 5 retries, 2s initial backoff, x2 multiplier
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 25 (Observability), all subscriber blocks
agents: Systems Agent, Infrastructure Agent
---

## Context
D-031 established the retry-with-exponential-backoff pattern but left the
specific parameters to be declared before Block 13 build begins.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Block 13 retry parameters: 5 retries, 2-second initial backoff, ×2
multiplier. Ceiling approximately 60 seconds, total exposure approximately
2 minutes. After retry exhaustion, event is placed in dead-letter state,
logged, and owner notified via Block 4 (D-031).

## Rationale
For a single-owner personal system, the primary failure scenario is a block
restarting or briefly degraded. 5 retries over ~2 minutes gives meaningful
tolerance for transient issues while surfacing real failures promptly. 2s
initial interval avoids hammering a struggling block. Simple doubling is
the easiest backoff curve to trace in logs.

## Consequences
Rules out retry counts, intervals, or multipliers other than those declared
here without a superseding decision.

## Related Decisions
D-031 (retry with exponential backoff),
D-028 (queue overflow backpressure).
