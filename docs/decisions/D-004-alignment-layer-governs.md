---
id: D-004
title: Alignment Layer governs the goal function; Evolution Engine may not modify ends
status: Accepted
date: 2026-05-01
blocks: Block 22 (Alignment Layer), Block 21 (Evolution Engine)
agents: All agents — constrains what the Evolution Engine may optimise;
        Architect owns Block 22
---

## Context
An Evolution Engine that can modify its own goals is the TechnoCore failure
mode — the explicit anti-pattern for CLIVE. A clear boundary between
optimising means and modifying ends must be established before any evolution
mechanism is designed.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Alignment Layer (Block 22) governs the goal function. The Evolution
Engine (Block 21) may optimise means but cannot modify ends.

## Rationale
The TechnoCore failure mode — hidden optimisation targets — is the explicit
anti-pattern. This boundary must be structural, not reliant on policy alone.

## Consequences
Rules out any evolutionary mechanism that modifies the alignment constitution.
Rules out any agent or worker that can alter its own declared purpose. The
alignment constitution may only be changed by the owner.

## Related Decisions
D-012 (Architect co-owns Block 22), D-022 (experimental zone isolation),
D-029 (Block 21 parameterised IaC templates), D-034 (owner sign-off per
promotion), D-037 (alignment gate is deterministic rules), D-038 (D-034
relaxation requires explicit decision).
