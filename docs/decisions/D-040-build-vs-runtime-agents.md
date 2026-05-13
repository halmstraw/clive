---
id: D-040
title: Build-phase agents and runtime workers are explicitly distinct models
status: Accepted
date: 2026-05-01
blocks: Block 10 (Workers), Block 13 (Orchestrator), Block 17 (Tool Registry),
        Block 29 (Documentation)
agents: All agents — clarifies the role boundary for build vs runtime
---

## Context
Without naming the split between build-phase and runtime models, the build
risks assuming both coexist, and risks treating the Architect as a runtime
entity that holds state between sessions — a violation of D-018.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The build-phase agent model and the runtime worker model are explicitly
distinct. The Architect and the seven Specialist agents are build-phase
design roles instantiated as Claude conversations mediated by the owner.
They produce requirements, decisions, and worker specifications; they do
not exist at runtime. Runtime workers (Block 10) are deployed as event bus
subscribers, designed by Specialists during build but instantiated as
separate runtime entities.

## Rationale
Build agents produce design artefacts under owner mediation; runtime workers
execute under event bus governance. Conflating the two produces a system
that violates D-018 at the first attempt to have the Architect "remember"
something between sessions.

## Consequences
Rules out the Architect or Specialists existing as runtime processes. Rules
out runtime workers instantiated through chat sessions. Rules out any
build-phase agent retaining state between sessions outside the central store.

## Related Decisions
D-018 (agents are stateless), D-009 (build model A).
