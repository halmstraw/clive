---
id: D-069
title: Infrastructure Agent must include separate backup for S3 raw store in IaC design
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 16 (Storage)
agents: Infrastructure Agent, Knowledge Agent
---

## Context
D-068 explicitly rules out raw store approaches that are not independently
backupable. D-056 defines the 24-hour recovery window for Block 16 as a
whole. Without an explicit decision, the object store backup could be
overlooked as an implementation detail.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Infrastructure Agent must include a separate backup mechanism for the
S3-compatible object store (raw store, D-068) in its Block 27 IaC design.
The nightly PostgreSQL snapshot (D-056) does not cover object storage. Both
stores must be recoverable to the same point in time.

## Rationale
D-068 explicitly rules out raw store approaches that are not independently
backupable. D-056 defines the 24-hour recovery window for Block 16 as a
whole. The object store sitting outside PostgreSQL creates a gap if backup
is not explicitly provisioned.

## Consequences
Rules out treating the nightly PostgreSQL snapshot as sufficient coverage
for Block 16 recovery. Rules out any IaC design where the raw store has no
declared backup mechanism.

## Related Decisions
D-056 (24-hour data loss window), D-068 (S3 raw store),
D-089 (dedicated backup credentials).
