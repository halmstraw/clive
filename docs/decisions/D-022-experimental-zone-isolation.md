---
id: D-022
title: Experimental zone runs on entirely separate infrastructure from production
status: Accepted
date: 2026-05-01
blocks: Block 21 (Evolution Engine), Block 24 (Sandboxing),
        Block 27 (Infrastructure/IaC), Block 22 (Alignment Layer)
agents: Systems Agent (Block 21), Access & Security Agent (Block 24),
        Infrastructure Agent (Block 27), Architect (Block 22)
---

## Context
The Evolution Engine runs untested variants. If experimental infrastructure
shares any resources with production, a misbehaving variant can affect
production state. Policy-only isolation cannot be verified by the alignment
layer without creating a circular dependency.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The experimental zone (Blocks 21 and 24) runs in entirely separate
infrastructure from production. Separate network, separate accounts, no
shared resources.

## Rationale
Policy-only isolation creates a circular dependency the alignment layer
cannot resolve.

## Consequences
Rules out partition-only or policy-only isolation. Rules out any shared
infrastructure between experimental and production. The event bridge
(D-024) is the only connection between the two environments.

## Related Decisions
D-004 (alignment boundary), D-024 (controlled event bridge),
D-029 (Block 21 parameterised IaC), D-030 (experimental events trust
class), D-032 (Block 25 production-scoped only).
