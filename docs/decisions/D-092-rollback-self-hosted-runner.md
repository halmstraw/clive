---
id: D-092
title: rollback.yml updated to use self-hosted runner
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
D-090 established that all deploy jobs run on the self-hosted runner.
`rollback.yml` was using a GitHub-hosted runner, creating an inconsistency.
A rollback must execute on the same runner as a deploy, or it cannot access
the VM's local Docker environment.

## Options Considered
A. Update rollback.yml to use self-hosted runner (chosen) — consistent with
   D-090; rollback executes in the same environment as deploy.
B. Keep rollback.yml on GitHub-hosted runner — inconsistent with D-090;
   rollback would have no access to the VM.

## Decision
`rollback.yml` is updated to use the self-hosted runner. All CI/CD jobs that
touch the VM — including rollback — run on the self-hosted runner consistent
with D-090.

## Rationale
Consistency with D-090. A rollback that cannot reach the VM is not a rollback.
The self-hosted runner runs on the VM and has direct access to the Docker
environment, which rollback requires.

## Consequences
Rules out any rollback job running on a GitHub-hosted runner. Rules out
any CI/CD job that touches the VM running on a GitHub-hosted runner.

## Related Decisions
D-090 (self-hosted runner), D-075 (GitHub Actions).
