---
id: D-017
title: Block 13 and Block 16 are built first; not deferred
status: Accepted
date: 2026-05-01
blocks: Block 13 (Central Orchestrator), Block 16 (Storage)
agents: Systems Agent (Block 13 owner), Knowledge Agent (Block 16 owner)
---

## Context
All other blocks depend on the event bus (Block 13) to communicate and on
storage (Block 16) to persist state. Building anything else first creates
a substrate that cannot wire together.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Block 13 (Central Orchestrator) and Block 16 (Storage) are the first things
built. They are not deferred.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out treating build infrastructure as separate from CLIVE's
architecture. Rules out deferring Block 13 and Block 16 to make faster
surface-level progress.

## Related Decisions
D-019 (Systems and Infrastructure Agents activated first),
D-021 (implementation waits for requirements),
D-023 (single orchestrator instance), D-062 (in-process event bus).
