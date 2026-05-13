---
id: D-074
title: CLIVE v0.1 has no staging environment; CI deploys direct to production
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD), Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent
---

## Context
A staging environment would add cost and operational overhead. For a
single-owner personal system at v0.1, the risk profile must be weighed
against that overhead.

## Options Considered
A. No staging, automated tests plus rollback as safety net (chosen) —
   consistent with D-023 simplicity; appropriate risk management for v0.1.
B. Separate staging VM — ongoing cost and operational overhead before there
   is evidence deployment failure rate justifies it.

## Decision
CLIVE v0.1 has no staging environment. The CI/CD pipeline deploys direct
to production after passing automated tests. Rollback capability (Block 28)
is the safety net.

## Rationale
For a single-owner personal system at v0.1, automated tests plus rollback
is the correct risk management approach. A staging environment adds ongoing
cost and operational overhead before there is evidence the deployment failure
rate justifies it. Consistent with D-023's simplicity preference.

## Consequences
Rules out a separate staging VM or environment at v0.1. Rules out any
pipeline step that requires a staging promotion before production deploy.
Revisit post-v0.1 if production deployment failures prove a real problem.

## Related Decisions
D-023 (single instance simplicity), D-075 (GitHub Actions),
D-092 (rollback.yml).
