---
id: D-038
title: D-034 relaxation requires explicit superseding decision reviewing full history
status: Accepted
date: 2026-05-01
blocks: Block 21 (Evolution Engine), Block 22 (Alignment Layer),
        Block 9 (Action Layer), Block 28 (CI/CD)
agents: Systems Agent, Architect, Intelligence Agent, Infrastructure Agent
---

## Context
As evolution volume grows, natural pressure will build toward relaxing
the per-promotion owner sign-off required by D-034. Without a deliberate
brake, D-034 will erode into rubber-stamping over time.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
D-034 cannot be relaxed without an explicit superseding decision that
reviews the full intervening evolution history and names concrete relaxation
criteria. Any future move toward policy-level or tiered promotion approval
requires a discrete decision entry, not gradual practice change.

## Rationale
Making relaxation expensive — by requiring an explicit decision that reviews
evidence — preserves the alignment guarantee D-034 provides. The relaxation
criteria are best written when there is actual evolution history to look at,
not in advance.

## Consequences
Rules out implicit relaxation of D-034 through changed practice. Rules out
Architect or specialist autonomy to soften D-034 without owner sign-off via
explicit decision entry. Rules out any promotion pathway that bypasses owner
sign-off without a discrete superseding decision.

## Related Decisions
D-034 (owner sign-off per promotion), D-004 (alignment boundary).
