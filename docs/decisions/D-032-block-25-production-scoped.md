---
id: D-032
title: Block 25 is production-scoped only; evolution history crosses bridge as events
status: Accepted
date: 2026-05-01
blocks: Block 25 (Observability), Block 21 (Evolution Engine),
        Block 13 (Orchestrator), Block 22 (Alignment Layer),
        Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent (Block 25, Block 27),
        Systems Agent (Block 21, Block 13), Architect (Block 22)
---

## Context
The owner needs a unified view of evolution history. But spanning Block 25
across both environments would create a second cross-environment connection,
violating D-022's structural separation.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Block 25 (Observability) is production-scoped only. Block 21 emits a
standardised evolution-history event type that crosses the event bridge
into production. Block 25 ingests these bridge-origin events as a
first-class data source and presents a unified view to the owner.
Block 25 does not span experimental infrastructure.

## Rationale
Allowing Block 25 to span both environments would create a second
cross-environment connection alongside the bridge, violating D-022.
Evolution-history events crossing the bridge remain subject to the enhanced
alignment gate (D-030), so unified owner visibility is achieved without
compromising environmental isolation.

## Consequences
Rules out Block 25 deployed into or connected to experimental
infrastructure. Rules out any observability mechanism that creates a second
cross-environment channel. Rules out evolution history being visible to the
owner only through experimental-zone tooling.

## Related Decisions
D-022 (experimental zone isolation), D-024 (controlled event bridge),
D-030 (experimental events trust class).
