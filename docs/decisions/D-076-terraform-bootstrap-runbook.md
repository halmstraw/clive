---
id: D-076
title: Terraform state bucket bootstrap is manual one-time step; must be in runbook
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 29 (Documentation)
agents: Infrastructure Agent
---

## Context
The Terraform remote state bucket must exist before the first `terraform apply`,
but it cannot be created by Terraform itself (circular dependency). This manual
prerequisite must be captured or it will cause a failed first deployment.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Terraform remote state bucket bootstrap is a required manual one-time
step that must be completed before the first `terraform apply`. It is not
managed by Terraform itself. This step must be documented as an operational
runbook entry in Block 29 (Documentation). The Infrastructure Agent is
responsible for producing the runbook content; Block 29 is the owner.

## Rationale
A manual prerequisite not captured in IaC or a runbook is an invisible
dependency that will cause a failed first deployment. Naming Block 29 as
owner ensures the step is written down, versioned, and findable before the
first deploy attempt.

## Consequences
Rules out treating the bootstrap as an implicit step known only from the
artefact note. Rules out any first `terraform apply` attempt without the
runbook entry existing and confirmed.

## Related Decisions
D-071 (Terraform), D-086 (no state locking).
