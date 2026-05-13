---
id: D-056
title: Maximum data loss window is 24 hours; nightly snapshot backup only
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 27 (Infrastructure/IaC)
agents: Knowledge Agent, Infrastructure Agent
---

## Context
D-027 requires a declared maximum data loss window before Block 16 and
Block 27 implementation begins. The specific window must balance simplicity
against the value of accumulated knowledge.

## Options Considered
A. 24-hour window, nightly snapshot only (chosen) — consistent with D-023
   simplicity preference; most v0.1 knowledge is re-ingestable.
B. 1-hour window, continuous log shipping — accurate but adds infrastructure
   overhead before there is evidence of need.
C. Unbounded — explicitly ruled out by D-027.

## Decision
Maximum acceptable data loss window for Block 16 is 24 hours. Nightly
snapshot backup only. No continuous log shipping at v0.1.

## Rationale
Consistent with D-023's v1 simplicity preference. Most of CLIVE's knowledge
at v0.1 comes from external sources that can be re-ingested. A nightly
snapshot preserves the prior day's audit record. 24 hours rules out
unbounded loss without continuous infrastructure overhead.

## Consequences
Rules out unbounded data loss. Rules out continuous WAL shipping or
equivalent at v0.1. Rules out any recovery window longer than 24 hours.
Continuous shipping is a v2 consideration once ingestion volume is known.

## Related Decisions
D-027 (point-in-time recovery), D-068 (S3 raw store),
D-069 (object store backup requirement).
