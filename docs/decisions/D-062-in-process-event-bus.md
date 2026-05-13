---
id: D-062
title: Block 13 event bus is in-process pub/sub; no external broker
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 27 (Infrastructure/IaC),
        Block 25 (Observability)
agents: Systems Agent, Infrastructure Agent
---

## Context
At v0.1, CLIVE is single-surface and query-only with one primary subscriber
(Block 8) and one orchestrator-mediated sub-call (D-043). An external broker
would add infrastructure complexity and a network hop with no proportionate
benefit.

## Options Considered
A. In-process pub/sub inside orchestrator process (chosen) — simplest;
   consistent with D-023; failure mode matches single-instance decision.
B. External broker (e.g. Redis Streams) — additional service to operate;
   network hop; premature at v0.1 scale.
C. Cloud-managed queue service — network hop; external service dependency;
   inconsistent with D-023.

## Decision
Block 13's event bus is implemented as an in-process pub/sub mechanism
running inside the orchestrator process. No external broker. Events are
function calls within the process, logged to Block 16 before dispatch.

## Rationale
At v0.1, the in-process bus is the simplest implementation consistent with
D-023's simplicity preference. The failure mode — orchestrator process down
means bus down — is already true under D-023's single-instance decision.
Migration to an embedded broker is a well-understood path if resilience
proves a real need post-v0.1.

## Consequences
Rules out external message broker at v0.1. Rules out cloud-managed queue
service at v0.1. Rules out any event routing that introduces a network hop
between emitter and orchestrator.

## Related Decisions
D-023 (single orchestrator instance), D-063 (long-running container),
D-064 (single cloud VM).
