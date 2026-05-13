---
id: D-042
title: Intelligence Agent and Knowledge Agent activated; Block 21 paused
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 16 (Storage), Block 21 (Evolution Engine),
        Block 29 (Documentation)
agents: Intelligence Agent (activated), Knowledge Agent (activated),
        Systems Agent (Block 21 paused)
---

## Context
Four of six v0.1 critical path blocks (1, 8, 16, 23) had no requirements
depth. Two new agent activations were needed to unblock the biggest unknowns
without overloading coordination.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Intelligence Agent activated (Blocks 8–12, Block 8 first priority) and
Knowledge Agent activated (Blocks 14–18, Block 16 first priority). Systems
Agent paused on Block 21 — not on v0.1 critical path (D-035). Agent prompts
moved to Notion as individual pages, with AGENT_PROMPTS_POINTER.md replacing
CLIVE_Agent_Prompts_v2.md as the project file reference.

## Rationale
Activating Intelligence and Knowledge agents unblocks the two biggest
unknowns (Block 8 and Block 16) while keeping coordination load manageable.
Pausing Block 21 focuses the Systems Agent's capacity on v0.1 critical path.
Notion-hosted prompts are consistent with D-033 — single source of truth,
not stale project files.

## Consequences
Rules out continuing Block 21 work before v0.1 ships. Rules out treating
CLIVE_Agent_Prompts_v2.md as the authoritative prompt source.

## Related Decisions
D-013 (specialist activation), D-015 (incremental growth),
D-035 (v0.1 scope).
