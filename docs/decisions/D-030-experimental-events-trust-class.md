---
id: D-030
title: Experimental zone events are a distinct trust class; enhanced alignment gate applies
status: Accepted
date: 2026-05-01
blocks: Block 22 (Alignment Layer), Block 13 (Orchestrator),
        Block 21 (Evolution Engine), Block 27 (Infrastructure/IaC)
agents: Architect (Block 22), Systems Agent (Block 13, Block 21),
        Infrastructure Agent (Block 27)
---

## Context
Production events come from human-reviewed, IaC-deployed code. Experimental
events come from evolutionary processes that may have discovered unexpected
paths to achieve fitness criteria. Treating them identically risks the
TechnoCore failure mode in its earliest form.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Experimental zone events are a distinct trust class from production events.
Block 13 identifies bridge-origin events via explicit provenance metadata
in the event schema. Bridge-origin events route through an enhanced alignment
gate — stricter than the standard production check — before entering the
production event bus. Closed-failure applies if the gate cannot positively
confirm the event is safe.

## Rationale
Production block emissions originate from human-reviewed code. Experimental
variant outputs may have found unexpected optimisation paths. An experimental
variant influencing production state in unanticipated ways is the TechnoCore
failure mode in its earliest form. Stricter scrutiny at the bridge crossing
is the correct response.

## Consequences
Rules out treating bridge-origin events identically to production events.
Rules out any bridge-origin event influencing production state without
passing an enhanced alignment check. Rules out silent passage of
experimental results into production.

## Related Decisions
D-004 (alignment boundary), D-022 (experimental zone isolation),
D-024 (controlled event bridge), D-037 (alignment gate mechanism).
