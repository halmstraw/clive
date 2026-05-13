---
id: D-027
title: v1 disaster recovery is point-in-time; recovery time may be hours
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 27 (Infrastructure/IaC)
agents: Knowledge Agent, Infrastructure Agent
---

## Context
A system whose primary value is accumulated knowledge cannot accept
unbounded data loss. But full infrastructure snapshots add complexity
inconsistent with D-023's simplicity preference.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
CLIVE v1 disaster recovery scope is point-in-time recovery. Production
storage (Block 16) is backed up with sufficient frequency to recover to
a recent known-good state. Infrastructure is rebuilt from IaC (Block 27)
if lost. Recovery time may be hours. Data loss is bounded to a declared
maximum window.

## Rationale
Unbounded data loss is unacceptable for a system whose primary value is
accumulated knowledge. Full infrastructure snapshots add complexity
inconsistent with D-023. Brief downtime is acceptable for a single-owner
system; significant knowledge loss is not.

## Consequences
Rules out hot standby recovery in v1. Rules out full infrastructure
snapshots in v1. Rules out accepting unbounded data loss. D-056 declares
the specific recovery window (24 hours).

## Related Decisions
D-056 (24-hour data loss window), D-068 (S3 raw store),
D-069 (object store backup requirement).
