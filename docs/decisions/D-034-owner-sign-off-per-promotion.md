---
id: D-034
title: Every variant promotion from experimental requires explicit owner sign-off
status: Accepted
date: 2026-05-01
blocks: Block 21 (Evolution Engine), Block 9 (Action Layer),
        Block 22 (Alignment Layer), Block 28 (CI/CD)
agents: Systems Agent (Block 21), Intelligence Agent (Block 9),
        Architect (Block 22), Infrastructure Agent (Block 28)
---

## Context
The Evolution Engine discovers variants that outperform current production
code. Without a clear promotion gate, variants could influence production
behaviour autonomously.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Every variant promotion from experimental to production requires explicit
owner sign-off as a discrete approval event. Block 21 proposes; it does
not self-promote. The confirmation gate is implemented via Block 9.
Policy-level and tiered promotion models are deferred to v2.

## Rationale
This is an alignment constraint, not solely a D-006 question. Autonomous
promotion produces production behaviour changes the owner has not
individually reviewed, which is a form of opacity inconsistent with the
alignment constitution. Rollback via Block 28 is a correction mechanism,
not a substitute for prior owner awareness.

## Consequences
Rules out policy-level promotion approval in v1. Rules out tiered promotion
models in v1. Rules out any Block 21 pathway that changes production
behaviour without a discrete owner approval event.

## Related Decisions
D-004 (alignment boundary), D-006 (confirmation gate),
D-038 (D-034 relaxation requires explicit superseding decision).
