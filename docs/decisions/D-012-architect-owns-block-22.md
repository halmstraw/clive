---
id: D-012
title: Architect co-owns Block 22; Systems Agent owns Blocks 13 19 20 21 only
status: Accepted
date: 2026-05-01
blocks: Block 22 (Alignment Layer), Block 13 (Orchestrator),
        Block 19 (Config/Admin), Block 20 (Cost/Rate), Block 21 (Evolution Engine)
agents: Architect (co-owns Block 22), Systems Agent (Blocks 13/19/20/21 only)
---

## Context
The alignment constitution is CLIVE's most sensitive artefact. Assigning it
to a specialist creates a risk that implementation concerns influence
alignment semantics.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Architect co-owns Block 22. Block 22 is not assigned to any specialist.
The Systems Agent owns Blocks 13, 19, 20, 21 only.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out any specialist owning or modifying the alignment constitution.
The owner is the only person who can change the alignment constitution;
the Architect is the only agent who may author alignment gate rules.

## Related Decisions
D-004 (Alignment Layer governs goal function), D-013 (specialist
activation), D-060 (Architect authors Block 22 alignment gate ruleset).
