---
id: D-099
title: CLIVE v0.2 scope approved
status: Accepted
date: 2026-05-09
blocks: All blocks
agents: All agents
---

## Context
CLIVE v0.1 was signed off (D-094). The next version scope must be defined
before v0.2 work begins.

## Options Considered
Not explicitly recorded in original decision entry.

## Decision
CLIVE v0.2 scope is approved. v0.2 adds:
- MinIO raw store (Block 16 object storage for raw ingested files)
- Block 14 ingestion pipeline end-to-end
- Block 15 processing pipeline (chunking and embedding)
- Telegram /ingest command (Block 23 surface for file ingestion)

v0.2 does not include Block 18 (Feedback/Correction) — deferred to v0.3
per D-100.

## Rationale
Logical next step after v0.1. Completes the knowledge ingestion pipeline
end-to-end, enabling CLIVE to learn from documents the owner provides.

## Consequences
v0.2 work may begin immediately. Block 18 is out of v0.2 scope per D-100.
v0.2 completion criteria to be defined as blocks are implemented.

## Related Decisions
D-094 (v0.1 signed off), D-100 (Block 18 deferred to v0.3),
D-101 (Telegram /ingest command pattern).
