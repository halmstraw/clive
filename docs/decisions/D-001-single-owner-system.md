---
id: D-001
title: CLIVE is a single-owner system
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents
---

## Context
Designing a personal AI system raises an early question about whether it
should serve one person or multiple. Multi-user support would affect alignment
modelling, identity handling, and goal conflict resolution from the start.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
CLIVE is a single-owner system. Multi-user is explicitly a future
consideration, not a current requirement.

## Rationale
Alignment is simpler when there is one declared intent. Multi-user introduces
conflicting goals, which the current alignment model does not handle.

## Consequences
Rules out shared instances, family plans, and team accounts in v1. Any
multi-user capability requires a new decision before entering scope.

## Related Decisions
D-004 (Alignment Layer governs goal function), D-035 (v0.1 scope),
D-036 (Business Layer out of v1 scope).
