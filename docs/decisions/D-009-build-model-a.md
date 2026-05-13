---
id: D-009
title: Build team follows Model A — parallel specialists coordinated by owner and Architect
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — defines the coordination model for the entire build
---

## Context
A multi-agent build requires a coordination model. Options range from fully
centralised (one lead agent) to fully distributed (agents coordinate directly)
to owner-mediated (owner coordinates with Architect support).

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The build team follows Model A: parallel specialist agents coordinated by
the owner, with one Architect agent for cross-block coherence.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out agent-to-agent direct coordination. Rules out a lead agent the
owner delegates to without visibility. The owner is always in the loop.

## Related Decisions
D-010 (standard decision protocol), D-011 (one ask per message),
D-013 (specialist activation on Architect recommendation),
D-016 (parallel build process), D-040 (build vs runtime agents).
