---
id: D-019
title: Systems Agent and Infrastructure Agent activated first
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 27 (Infrastructure/IaC)
agents: Systems Agent, Infrastructure Agent
---

## Context
No other specialist can contribute meaningfully until Block 13 (the event
bus) and foundational infrastructure (Block 27) are operational. Activating
other specialists before that substrate exists produces design work with
nowhere to land.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Systems Agent and Infrastructure Agent are the first specialists
activated. No other specialist activates until Block 13 and foundational
infrastructure are operational.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out activating any other specialist before the substrate exists.
Enforces the dependency order implied by D-017.

## Related Decisions
D-013 (activation process), D-015 (incremental specialist growth),
D-017 (Block 13 and Block 16 built first).
