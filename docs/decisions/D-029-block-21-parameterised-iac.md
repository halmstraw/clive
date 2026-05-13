---
id: D-029
title: Block 21 provisions experimental environments using parameterised IaC templates only
status: Accepted
date: 2026-05-01
blocks: Block 21 (Evolution Engine), Block 24 (Sandboxing),
        Block 27 (Infrastructure/IaC), Block 22 (Alignment Layer)
agents: Systems Agent (Block 21), Infrastructure Agent (Block 27),
        Architect (Block 22)
---

## Context
The Evolution Engine needs to provision experimental environments. Allowing
it to define arbitrary infrastructure would produce environments that have
never been reviewed by a human, violating D-004.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Block 21 may only request experimental environment provisioning using
parameterised IaC templates. Block 21 selects a template and may vary
declared parameters within IaC-defined structural caps (e.g. compute size,
duration). Template shapes are defined, reviewed, and promoted through the
normal IaC pipeline. Block 21 does not define infrastructure.

## Rationale
Arbitrary infrastructure configuration allows the Evolution Engine to
provision environments that have never been reviewed, violating D-004.
Parameterised templates give Block 21 meaningful flexibility while keeping
infrastructure shapes under human review.

## Consequences
Rules out Block 21 specifying arbitrary infrastructure configurations.
Rules out sandbox provisioning outside pre-declared IaC templates. Rules
out infrastructure shapes that have not passed through the IaC pipeline.

## Related Decisions
D-004 (alignment boundary), D-022 (experimental zone isolation),
D-024 (controlled event bridge), D-034 (owner sign-off per promotion).
