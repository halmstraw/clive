---
id: D-064
title: CLIVE v0.1 runs on a single cloud VM
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 13 (Orchestrator), Block 28 (CI/CD)
agents: Infrastructure Agent, Systems Agent
---

## Context
The deployment target must be always-on, recoverable from IaC if lost, and
not dependent on the owner's physical hardware being available.

## Options Considered
A. Single cloud VM (chosen) — always on; recoverable from IaC; consistent
   with D-023 simplicity preference.
B. Owner local hardware — not always on; physical availability dependency;
   violates IaC recovery requirement.
C. Multi-VM or orchestrated cluster — unnecessary complexity at v0.1 scale.

## Decision
CLIVE v0.1 runs on a single cloud VM. All v0.1 services run as containers
on one rented virtual machine.

## Rationale
A single cloud VM is always on, recoverable from IaC if lost (D-027), and
does not depend on physical hardware availability. Consistent with D-023
(single instance, simplicity preference) and D-063 (long-running
containerised service).

## Consequences
Rules out owner local hardware as the v0.1 deployment target. Rules out
multi-VM or orchestrated cluster deployments at v0.1.

## Related Decisions
D-023 (single orchestrator instance), D-063 (long-running container),
D-070 (Hetzner), D-072 (Compose + Ansible).
