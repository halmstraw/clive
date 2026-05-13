---
id: D-060
title: Architect authors Block 22 alignment gate ruleset; Systems Agent implements only
status: Accepted
date: 2026-05-01
blocks: Block 22 (Alignment Layer), Block 13 (Orchestrator), Block 29 (Documentation)
agents: Architect (Block 22 owner and ruleset author),
        Systems Agent (Block 13 implementer)
---

## Context
D-037 established that the alignment gate is deterministic rules. The
question of who authors and maintains those rules must be settled before
Block 22 and Block 13 implementation begins.

## Options Considered
A. Architect authors the ruleset; Systems Agent implements (chosen) —
   authorship aligned with Block 22 ownership.
B. Systems Agent authors the ruleset as part of Block 13 implementation —
   gives an implementation agent influence over alignment semantics;
   inconsistent with D-012 and D-004.

## Decision
The Architect authors and maintains the ruleset that populates the Block 22
alignment gate. The ruleset translates the alignment constitution into
deterministic rules checked against event effect types (D-037). Owner
approval is required for any change to the ruleset. The Systems Agent
implements the gate mechanism in Block 13 and receives the ruleset as a
constraint; it does not author alignment rules.

## Rationale
The alignment gate ruleset is an expression of the alignment constitution,
not an implementation detail. Authorship belongs with Block 22 ownership.
Delegating ruleset authorship to the Systems Agent would give an
implementation agent influence over alignment semantics — inconsistent with
D-012 and D-004.

## Consequences
Rules out the Systems Agent authoring or modifying alignment gate rules.
Rules out any change to the ruleset without owner approval and a
corresponding decision entry. Rules out the ruleset being treated as an
implementation detail owned by Block 13.

## Related Decisions
D-004 (alignment boundary), D-012 (Architect co-owns Block 22),
D-037 (alignment gate mechanism).
