---
id: D-002
title: No technology choices at specification stage
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — constrains all specialists during requirements work
---

## Context
Requirements work for each block must not be constrained by premature
technology decisions. Naming specific tools or platforms during specification
creates lock-in before the problem is well-understood.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
No technology choices are made at specification stage. Technology is selected
when requirements are sufficiently understood, potentially informed by the
Evolution Engine.

## Rationale
Premature technology lock-in is a known failure mode. The system should
choose its own tools where possible.

## Consequences
Rules out naming specific databases, LLM providers, cloud platforms, or
frameworks in requirements documents. Technology decisions come later and
are recorded as separate decision entries.

## Related Decisions
D-021 (implementation does not begin until requirements are deepened),
D-037 (alignment gate mechanism class decided before tooling),
D-077 (LiteLLM abstraction).
