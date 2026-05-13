---
id: D-059
title: Alert payload schema between Block 25 and Block 4 is jointly-owned interface contract
status: Accepted
date: 2026-05-01
blocks: Block 25 (Observability), Block 4 (Interface/Egress),
        Block 13 (Orchestrator), Block 29 (Documentation)
agents: Infrastructure Agent (Block 25), Experience Agent (Block 4),
        Systems Agent (Block 13)
---

## Context
Alerts are a two-party interface — Block 25 must express what it knows;
Block 4 must render it coherently for the owner. Unilateral ownership by
either party creates a dependency risk.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The alert payload schema between Block 25 (Observability) and Block 4
(Interface/Egress) is a jointly-owned interface contract, recorded as an
interface specification in Block 29 (Documentation). Neither Block 25 nor
Block 4 may change the schema unilaterally. Any change requires a decision
entry and both specialist agents to acknowledge the revision before
implementation.

## Rationale
Alerts are a two-party interface — Block 25 must express what it knows;
Block 4 must render it coherently for the owner. Unilateral ownership by
either party creates a dependency risk: Block 25 could emit alerts Block 4
cannot render, or Block 4 could change rendering assumptions Block 25 has
not been told about.

## Consequences
Rules out Block 25 unilaterally defining alert payload structure. Rules out
Block 4 unilaterally defining alert rendering requirements. Rules out any
alert schema change that does not produce a corresponding update to the
Block 29 interface specification and a decision entry.

## Related Decisions
D-073 (placeholder alert schema), D-078 (schema confirmed as contract).
