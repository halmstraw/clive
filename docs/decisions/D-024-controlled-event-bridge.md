---
id: D-024
title: Cross-environment communication via controlled event bridge only; fully logged
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 21 (Evolution Engine),
        Block 24 (Sandboxing), Block 27 (Infrastructure/IaC),
        Block 22 (Alignment Layer)
agents: Systems Agent, Infrastructure Agent, Architect
---

## Context
D-022 establishes that experimental and production environments are fully
separated. However, experimental results must be able to reach production
for the Evolution Engine to be useful. An uncontrolled connection would
undermine the isolation guarantee.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Cross-environment communication between production and experimental is
governed by a controlled event bridge. No shared storage or compute. The
bridge is the only connection and is fully logged.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out shared storage between environments. Rules out unlogged
cross-environment communication. All bridge traffic passes through the
enhanced alignment gate (D-030).

## Related Decisions
D-022 (experimental zone isolation), D-030 (experimental events trust
class), D-032 (Block 25 production-scoped only).
