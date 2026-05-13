---
id: D-016
title: Build process is parallel; specialist agents run concurrently
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — concurrent operation is the default pattern
---

## Context
A sequential build — one specialist completes before the next starts —
would extend the timeline unnecessarily when block groups have no
cross-dependencies at the requirements stage.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The build process is parallel. Specialist agents run concurrently across
their block groups.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out sequential specialist activation as the default pattern.
Coordination between active specialists routes through the owner and
Architect, not directly between agents.

## Related Decisions
D-009 (build model A), D-013 (specialist activation),
D-015 (incremental growth).
