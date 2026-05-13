---
id: D-073
title: Architect holds placeholder alert payload schema pending Experience Agent review
status: Accepted
date: 2026-05-01
blocks: Block 25 (Observability), Block 4 (Interface/Egress), Block 29 (Documentation)
agents: Architect (holds placeholder), Infrastructure Agent (Block 25),
        Experience Agent (Block 4, must review)
---

## Context
D-059 requires a jointly-owned alert schema, but the Experience Agent was
not in session when Block 25 implementation needed to begin. Blocking
implementation on an agent session is unnecessary.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Architect holds a placeholder alert payload schema on behalf of Block 25
and Block 4 until the Experience Agent formally reviews and adopts it. The
placeholder schema is sufficient to unblock Block 25 implementation. The
Experience Agent must review and either adopt or revise the schema in its
next session.

Placeholder schema fields:
- alert_id — uuid, unique per alert
- alert_type — string from constrained vocabulary: capacity_backpressure |
  dead_letter | health_degraded | cost_threshold | security_anomaly |
  infrastructure_change
- severity — enum: info | warn | error
- title — string, short human-readable summary
- body — string, full detail
- source_block — integer, originating block number
- timestamp — ISO8601
- conversation_id — uuid or null (present if alert is conversation-scoped)

## Rationale
D-059 requires a jointly-owned schema but the Experience Agent is not in
session. A conservative placeholder with mandatory review is the minimum
viable path that does not block Block 25 implementation.

## Consequences
Rules out Block 25 implementation proceeding without any declared alert
schema. Rules out the placeholder being treated as permanent without
Experience Agent review. Superseded for schema confirmation by D-078.

## Related Decisions
D-059 (jointly-owned alert schema), D-078 (schema confirmed as contract).
