---
id: D-087
title: Three Terraform configuration corrections during bootstrap; recorded for audit
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent
---

## Context
Three Terraform configuration corrections were required during the bootstrap
process. All are tooling/spec corrections, not design decisions.

## Options Considered
Not applicable — these are corrections to non-functional or deprecated
configuration, not choices between design options.

## Decision
Three Terraform configuration corrections made during bootstrap are recorded
for audit completeness:

(1) Server type corrected from `cx21` to `cpx22` (Regular Performance plan,
consistent with the Hetzner plan decision).

(2) Deprecated `endpoint` parameter replaced with `endpoints { s3 = ... }`.

(3) Deprecated `force_path_style` replaced with `use_path_style`.

(4) `skip_requesting_account_id = true` added (Hetzner is not AWS STS).

All are spec/tooling corrections, not design decisions.

## Rationale
Not applicable — all are corrections to deprecated or invalid configuration.

## Consequences
Rules out treating these as design changes. Rules out reverting any of
these corrections.

## Related Decisions
D-071 (Terraform), D-070 (Hetzner).
