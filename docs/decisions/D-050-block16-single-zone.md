---
id: D-050
title: Block 16 uses single zone "personal" at v0.1; zone enforcement active from day one
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 7 (Trust Zones), Block 13 (Orchestrator)
agents: Knowledge Agent (Block 16), Access & Security Agent (Block 7, future)
---

## Context
The full zone model (multiple zones, cross-zone queries, zone-specific
retention) is future scope. Deferring zone enforcement entirely would make
it a retrofit when multiple zones are introduced.

## Options Considered
A. Defer zone enforcement entirely to when multiple zones exist — creates
   a retrofit risk.
B. Single hard-coded zone, enforcement active from day one (chosen) —
   costs nothing, proves the mechanism before it matters.

## Decision
Block 16 uses a single hard-coded zone identifier ("personal") at v0.1.
Zone enforcement is active from day one — every retrieval request carries
a zone scope and Block 16 filters against it, even though only one zone
exists. The full zone model is deferred to the Access & Security Agent
when activated.

## Rationale
Exercising the zone interface with one zone costs nothing and proves the
enforcement mechanism before real zone boundaries matter. Deferring zone
enforcement entirely would make it a retrofit when multiple zones are
introduced.

## Consequences
Rules out deferring zone enforcement to post-v0.1. Rules out multiple zones
at v0.1. Rules out zone-unaware retrieval at any version.

## Related Decisions
D-043 (orchestrator-mediated retrieval), D-057 (channel-as-authentication).
