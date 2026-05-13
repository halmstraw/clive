---
id: D-090
title: CI/CD deploys via self-hosted GitHub Actions runner on VM; no inbound SSH
status: Accepted
date: 2026-05-01
blocks: Block 23 (Security), Block 27 (Infrastructure/IaC), Block 28 (CI/CD)
agents: Infrastructure Agent, Access & Security Agent (Block 23, future)
---

## Context
CI must deploy to the Hetzner VM. Options differ on how the connection is
established: inbound SSH, Tailscale overlay, webhook pull, or a runner
installed on the VM.

## Options Considered
A. Self-hosted runner on VM, outbound HTTPS only (chosen) — no inbound
   connections; no firewall changes; consistent with D-023 (simplicity).
B. Inbound SSH from GitHub Actions IP ranges — requires UFW rule additions;
   GitHub IP ranges are large and change.
C. Tailscale overlay — new account and service; not necessary at v0.1.
D. Webhook pull model — additional listener service on VM.

## Decision
CI/CD deploys to the VM via a self-hosted GitHub Actions runner installed
directly on the VM. Deploy jobs run locally on the VM. No inbound SSH from
GitHub Actions. The runner connects outbound to GitHub over HTTPS, which UFW
already permits. UFW remains locked to owner IP only with no additional
firewall rules required.

## Rationale
Simplest path for v0.1 — no new accounts, no firewall changes, no additional
listener services. The runner runs on already-trusted infrastructure.
Consistent with D-023 (simplicity) and the security posture of Block 23.

## Consequences
Rules out allowing GitHub Actions IP ranges in UFW. Rules out Tailscale at
v0.1. Rules out webhook pull model at v0.1. Rules out any inbound SSH from
GitHub Actions runners.

## Related Decisions
D-075 (GitHub Actions), D-092 (rollback.yml consistency).
