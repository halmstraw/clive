---
id: D-008
title: DECISIONS.md is a living document; every significant decision recorded before implementation
status: Accepted
date: 2026-05-01
blocks: Block 29 (Documentation)
agents: All agents — no agent implements before the decision is recorded
---

## Context
Design decisions made in chat transcripts are invisible to future sessions.
Without a persistent record, agents act on stale or forgotten rationale.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
DECISIONS.md is a living document, present in every chat. Every significant
decision is recorded here before implementation begins.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out implementing anything whose rationale exists only in a chat
transcript. Implementation without a recorded decision is a protocol
violation regardless of the decision's apparent clarity.

## Related Decisions
D-033 (Notion as previous source of truth for DECISIONS.md),
D-102 (migration to local ADR files — supersedes D-033).
