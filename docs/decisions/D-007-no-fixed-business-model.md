---
id: D-007
title: CLIVE has no fixed business model at initialisation
status: Accepted
date: 2026-05-01
blocks: Block 21 (Evolution Engine), Blocks 30–38 (Business Layer)
agents: Systems Agent (Block 21 owner), Business Agent (future, out of v1 scope)
---

## Context
Building a capable AI system raises the question of its commercial purpose.
Hardcoding a business model before the system is operational constrains what
it discovers it is good at.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
CLIVE has no fixed business model at initialisation. Business strategy is an
emergent property of the Evolution Engine.

## Rationale
The system should discover what it is good at rather than being constrained
to a predetermined commercial model.

## Consequences
Rules out hardcoded income strategies. Rules out business plans that cannot
be retired by the Reaper. D-036 places the Business Layer entirely out of
v1 scope.

## Related Decisions
D-036 (Business Layer out of v1 scope and gated behind named preconditions).
