---
id: D-086
title: Terraform state locking not implemented; Hetzner limitation accepted
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
Hetzner Object Storage does not support DynamoDB-style locking. State locking
prevents concurrent `terraform apply` operations from corrupting state.

## Options Considered
A. Accept lack of locking as known constraint (chosen) — D-001 makes
   concurrent operators impossible; risk is theoretical.
B. DynamoDB or equivalent locking backend — requires leaving Hetzner for
   this feature; inconsistent with D-070 and D-023.
C. Local lockfile conventions — process overhead with no real safety benefit
   for a single operator.

## Decision
Terraform state locking is not implemented. Hetzner Object Storage does not
support DynamoDB-style locking. This is accepted as a known constraint with
no mitigating action required.

## Rationale
State locking prevents concurrent `terraform apply` operations from corrupting
state. D-001 establishes CLIVE as a single-owner system with no concurrent
operators — the failure mode locking prevents cannot occur. D-023's simplicity
preference and D-070's Hetzner commitment rule out moving to a locking-capable
backend.

## Consequences
Rules out DynamoDB or equivalent locking backend. Rules out local lockfile
conventions. Rules out any backend migration to support locking at v0.1.

## Related Decisions
D-001 (single-owner), D-070 (Hetzner), D-071 (Terraform).
