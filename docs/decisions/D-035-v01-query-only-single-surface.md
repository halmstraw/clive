---
id: D-035
title: CLIVE v0.1 is single-surface query-only; zero actions workers or evolution
status: Accepted
date: 2026-05-01
blocks: Block 1 (Personality), Block 8 (Query/RAG), Block 13 (Orchestrator),
        Block 16 (Storage), Block 22 (Alignment Layer), Block 23 (Security)
agents: Experience Agent (Block 1, Block 23), Intelligence Agent (Block 8),
        Systems Agent (Block 13), Knowledge Agent (Block 16),
        Architect (Block 22)
---

## Context
Without a defined first user-visible milestone, the build risks becoming
infinite scaffolding. The scope of v0.1 must be small enough to ship but
meaningful enough to validate the substrate.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
CLIVE v0.1 is defined as a single-surface, query-only system. One channel
(surface choice deferred), Block 8 (Query/RAG) operating over a curated
knowledge base, with Block 1 personality intact. Zero actions, zero
workers, zero evolution at v0.1.

## Rationale
A query-only single-surface MVP proves the substrate (Blocks 1, 8, 13, 16,
22, 23) without dragging in Block 9's confirmation gate complexity or Block
10's scheduler. Smaller surface to validate alignment behaviour against
before adding any capability that can write, schedule, or evolve.

## Consequences
Rules out Action Layer (Block 9) at v0.1. Rules out worker scheduling
(Block 10) at v0.1. Rules out multiple surfaces at v0.1. Rules out
Evolution Engine (Block 21) operating at v0.1. Rules out specialist
activation for non-critical-path blocks before v0.1 ships.

## Related Decisions
D-061 (v0.1 surface is Telegram), D-080 (v0.1 acceptance criteria),
D-094 (v0.1 signed off 09 May 2026), D-099 (v0.2 scope).
