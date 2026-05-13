---
id: D-003
title: Event bus principle — all inter-block communication via Block 13
status: Accepted
date: 2026-05-01
blocks: Block 13 (Central Orchestrator), all blocks
agents: All agents — non-negotiable constraint on every design
---

## Context
A system with many blocks risks developing hidden direct dependencies between
them. These undermine observability, make alignment enforcement impossible,
and create implicit coupling that breaks independently.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The event bus principle is non-negotiable. No block communicates directly
with another block. All communication routes through the Central Orchestrator
(Block 13) via events.

## Rationale
Direct block-to-block calls create hidden dependencies, make alignment
enforcement impossible, and undermine observability.

## Consequences
Rules out shared databases as a communication mechanism, direct API calls
between blocks, and any pattern that bypasses the event bus. D-043 records
the one sanctioned exception pattern (orchestrator-mediated synchronous
sub-call) which satisfies this constraint.

## Related Decisions
D-017 (Block 13 built first), D-025 (at-least-once delivery),
D-026 (per-conversation ordering), D-043 (orchestrator-mediated retrieval).
