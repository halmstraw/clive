---
id: D-018
title: Agents are stateless API calls; all state lives in central store
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — no agent retains state between sessions
---

## Context
If agents retain state inside their own process or context, that state
is invisible to other sessions, cannot be backed up, and creates
inconsistency when the agent is replaced or restarted.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Agents are stateless API calls. All state lives in a central store
outside the agent.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out separate Claude accounts per agent. Rules out persistent agent
processes. Rules out agents remembering anything without explicit
injection from the central store.

## Related Decisions
D-033 (state in central store — Notion was that store for decisions),
D-040 (build-phase agents vs runtime workers),
D-102 (repo is now the central store for decision artefacts).
