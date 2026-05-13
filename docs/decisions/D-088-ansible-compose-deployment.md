---
id: D-088
title: Docker Compose stack deployment added as Ansible role; no manual step
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
D-072 declared the Terraform + Ansible + Compose stack but left the question
of who runs `docker compose up` on the VM. A manual step would be undeclared
and unreproducible.

## Options Considered
A. Ansible role to copy Compose file and run docker compose up (chosen) —
   one playbook run configures the VM end to end; consistent with D-072.
B. Manual Compose deployment after Ansible — undeclared; violates D-041.
C. Separate GitHub Actions job for Compose deployment — additional pipeline
   complexity; not needed when Ansible already runs on deploy.

## Decision
Docker Compose stack deployment is added as a role in the Ansible playbook.
Ansible copies the Compose file to the VM and runs `docker compose up`. One
playbook run configures the VM end to end. There is no separate manual Compose
deployment step.

## Rationale
Keeps the full VM configuration in one place and under one tool. Consistent
with D-072's declared Terraform + Ansible + Compose stack. A manual step
would be undeclared and unreproducible, violating D-041.

## Consequences
Rules out manual Compose deployment after Ansible. Rules out a separate
GitHub Actions job for Compose deployment at v0.1.

## Related Decisions
D-072 (Compose + Ansible), D-090 (self-hosted runner).
