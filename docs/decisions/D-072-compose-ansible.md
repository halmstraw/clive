---
id: D-072
title: Container management uses Docker Compose and Ansible; Terraform provisions VM
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
D-071 chose Terraform for VM provisioning. VM configuration (firewall, users,
software) and container management (running services) need separate tooling.

## Options Considered
A. Terraform + Ansible + Docker Compose (chosen) — standard single-VM
   pattern; each tool does one job; declared and reproducible.
B. Docker Compose without Ansible — VM configuration becomes undeclared
   manual steps; violates D-041.
C. Kubernetes / k3s — unnecessary orchestration complexity;
   inconsistent with D-023.

## Decision
Container management on the Hetzner VM uses Docker Compose for service
definitions and Ansible for VM configuration (users, firewall, software
installs). Terraform provisions the VM; Ansible configures it; Docker
Compose runs the services.

## Rationale
Compose alone leaves VM configuration as undeclared manual steps, violating
D-041's requirement for declared and enforced conventions. The Terraform +
Ansible + Compose stack is the standard pattern for a single-VM deployment —
each tool does one job.

## Consequences
Rules out Docker Compose without Ansible for VM configuration. Rules out
Kubernetes or any container orchestration platform at v0.1. Rules out manual
VM configuration steps outside Ansible.

## Related Decisions
D-071 (Terraform), D-088 (Ansible deploys Compose),
D-090 (self-hosted runner).
