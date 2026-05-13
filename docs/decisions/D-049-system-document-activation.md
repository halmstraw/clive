---
id: D-049
title: System document activation requires explicit two-step owner confirmation
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 22 (Alignment Layer), Block 1 (Personality),
        Block 9 (Action Layer, post-v0.1)
agents: Knowledge Agent, Architect, Experience Agent,
        Intelligence Agent (post-v0.1)
---

## Context
Changing the personality or alignment document changes everything Block 8
produces. This is consequential and effectively irreversible — it falls
under D-006 but Block 9 is not available at v0.1.

## Options Considered
A. Single-step submission-as-activation — silent behaviour change; violates
   D-006.
B. Two-step: submit then explicitly confirm (chosen) — preserves the D-006
   principle without requiring Block 9 at v0.1.
C. No confirmation mechanism until Block 9 is available — leaves v0.1 with
   no protection.

## Decision
Activating a new version of a system document requires explicit owner
confirmation as a separate step from submission. At v0.1: owner submits
the document (stored with is_active: false), then explicitly confirms
activation as a separate action. Post-v0.1, activation routes through
the Block 9 confirmation gate.

## Rationale
Changing the personality or alignment document changes everything Block 8
produces. This falls under D-006. Block 9 is not on the v0.1 critical path,
so the confirmation mechanism is a two-step configuration action, but the
principle — no silent behaviour change — is preserved.

## Consequences
Rules out single-step submission-as-activation. Rules out silent or automatic
version activation. Rules out bypassing confirmation for system document
changes at any version.

## Related Decisions
D-006 (confirmation gate), D-079 (v0.1 specific mechanism for this).
