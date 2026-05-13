---
id: D-091
title: Terraform CI plan auto; apply manual only
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
Terraform runs in CI. The question is whether `terraform apply` should run
automatically on push or require manual triggering. Auto-apply risks
unreviewed infrastructure changes being applied to production.

## Options Considered
A. Plan auto on push; apply is manual trigger only (chosen) — `terraform plan`
   runs automatically for visibility; `terraform apply` requires explicit
   manual dispatch.
B. Full auto-apply on push — no human review gate; risky for infrastructure
   changes.
C. Both plan and apply manual — loses the automatic plan output that surfaces
   drift and errors early.

## Decision
Terraform runs in CI as a separate job. `terraform plan` runs automatically
on push for visibility. `terraform apply` is manual only — it requires an
explicit manual trigger. No automated `terraform apply` on push.

## Rationale
Infrastructure changes are high-impact and hard to reverse. A plan-only auto
run surfaces drift and errors without risk. Manual apply preserves a human
review gate before any infrastructure change is committed. Consistent with
D-006 (confirmation gate) applied to infrastructure.

## Consequences
Rules out automated `terraform apply` on push. Rules out any CI configuration
that applies infrastructure changes without a manual trigger.

## Related Decisions
D-071 (Terraform), D-090 (self-hosted runner), D-006 (confirmation gate).
