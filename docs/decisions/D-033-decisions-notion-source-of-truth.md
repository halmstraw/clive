---
id: D-033
title: DECISIONS.md replaced by Notion pointer file; Notion is source of truth
status: Superseded by D-102
date: 2026-05-01
blocks: Block 29 (Documentation)
agents: All agents — changes session-start fetch procedure
---

## Context
Maintaining DECISIONS.md as a project file meant it drifted from Notion
immediately when new decisions were recorded. Agents reading a stale copy
could act on superseded decisions.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
DECISIONS.md is removed as a project file. It is replaced by a pointer
file (DECISIONS_POINTER.md) containing the Notion URL and an instruction
to the Architect to fetch live content at session start before acting.
Notion is the single source of truth for all decisions.

## Rationale
The project file copy drifts immediately as decisions are recorded in
Notion. A pointer with a fetch instruction is honest about where the truth
lives and consistent with D-018 — state lives in a central store, not
inside an agent's context.

## Consequences
Rules out maintaining DECISIONS.md as a project file. Rules out any agent
treating a project-file copy of decisions as authoritative. Rules out
session-end overwrites of the project file as a sync mechanism.

Superseded by D-102, which migrates the decision log from Notion to local
ADR files in the repository.

## Related Decisions
D-008 (decisions must be recorded before implementation),
D-018 (agents are stateless — state lives in central store),
D-102 (supersedes this decision — repo is now the source of truth).
