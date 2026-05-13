---
id: D-070
title: CLIVE v0.1 hosted on Hetzner
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent
---

## Context
D-064 established a single cloud VM as the deployment target. The cloud
provider must be chosen before Terraform configuration can begin.

## Options Considered
A. Hetzner (chosen) — lowest cost for required compute profile; European
   datacentre; no managed service lock-in; straightforward VM provisioning.
B. DigitalOcean — higher cost; no significant advantage at this scale.
C. AWS — higher cost; managed service complexity inconsistent with D-023.

## Decision
CLIVE v0.1 is hosted on Hetzner. The single cloud VM (D-064) is provisioned
on Hetzner infrastructure.

## Rationale
Lowest cost for the required compute profile, European datacentre,
straightforward VM provisioning, no managed service lock-in. Consistent
with D-023's simplicity preference and appropriate for a personal
single-owner system.

## Consequences
Rules out DigitalOcean, AWS, or any other cloud provider at v0.1 without
a superseding decision.

## Related Decisions
D-064 (single cloud VM), D-071 (Terraform for IaC),
D-083 (cliveai@proton.me infrastructure accounts).
