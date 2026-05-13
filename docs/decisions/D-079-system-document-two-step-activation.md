---
id: D-079
title: v0.1 system document activation is two-step — submit then confirm
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 22 (Alignment Layer), Block 1 (Personality),
        Block 9 (Action Layer, post-v0.1)
agents: Knowledge Agent, Architect, Experience Agent,
        Intelligence Agent (post-v0.1)
---

## Context
D-049 established the two-step confirmation principle for system document
activation. This decision records the specific v0.1 implementation
mechanism (without Block 9).

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The v0.1 mechanism for activating a system document (personality or
alignment rules) is a two-step configuration pathway: (1) owner submits
the new document version to Block 16, stored with is_active: false; (2)
owner explicitly confirms activation as a separate action, atomically
marking the new version active and the prior version inactive. Submission
alone does not activate. Post-v0.1, activation routes through Block 9.

## Rationale
Fully described in the Block 16 requirements artefact. Satisfies D-006
(confirmation gate) and D-049 (two-step principle) without requiring Block 9
at v0.1.

## Consequences
Rules out single-step submission-as-activation. Rules out silent or automatic
version activation. Rules out any activation pathway without a discrete owner
confirmation action.

## Related Decisions
D-006 (confirmation gate), D-049 (two-step activation principle).
