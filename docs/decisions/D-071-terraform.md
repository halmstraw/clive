---
id: D-071
title: Block 27 uses Terraform as IaC provisioning tool with Hetzner provider
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
D-064 and D-070 establish a single Hetzner VM. The IaC tool must declare
and reproduce that infrastructure without manual steps.

## Options Considered
A. Terraform with Hetzner provider (chosen) — mature provider; declarative
   model; well-understood by AI coding agents (D-009).
B. Pulumi — setup overhead without meaningful benefit at this scale.
C. Ansible-only — leaves VM provisioning unreproducible; violates D-041.

## Decision
Block 27 uses Terraform as the IaC provisioning tool. All infrastructure
definitions are written in Terraform. The Hetzner provider is used for VM
provisioning.

## Rationale
The Hetzner Terraform provider is mature. The declarative model maps cleanly
to D-041 (AI-optimised repo conventions) and is well-understood by AI coding
agents, which is the primary build mode (D-009). State file management on a
single VM is trivial.

## Consequences
Rules out Pulumi, Ansible-only, or any other IaC tool at v0.1 without a
superseding decision. Rules out manual VM provisioning outside Terraform.

## Related Decisions
D-070 (Hetzner), D-072 (Docker Compose + Ansible),
D-076 (Terraform bootstrap runbook), D-086 (no state locking).
