---
id: D-098
title: Maximum ingest file size 10 MB; oversized files rejected with ingest.rejected event
status: Accepted
date: 2026-05-01
blocks: Block 14 (Ingestion), Block 15 (Processing)
agents: Knowledge Agent
---

## Context
Ingest must impose a file size limit to prevent runaway processing costs and
memory pressure. The limit and the rejection behaviour must be defined.

## Options Considered
A. 10 MB limit; reject with ingest.rejected event (chosen) — round number;
   covers the expected document types at v0.1; rejection is observable via
   event bus.
B. No limit — risks runaway cost and memory pressure on single-VM deployment.
C. Smaller limit (1 MB) — too restrictive for PDFs and longer documents.

## Decision
The maximum ingest file size is 10 MB. Files exceeding this limit are rejected
before chunking. Block 14 emits an `ingest.rejected` event with the rejection
reason. No partial processing of oversized files.

## Rationale
10 MB covers all expected document types at v0.1 (text files, PDFs, markdown).
Rejection before chunking prevents any cost from being incurred. The
`ingest.rejected` event makes the rejection observable through the standard
event bus pattern (D-003).

## Consequences
Rules out ingest of files larger than 10 MB at v0.1. Rejection is clean — no
partial state. Limit may be revisited in v0.2 if large document support is
required.

## Related Decisions
D-097 (chunking), D-003 (event bus), D-014 (Block 14 ingestion).
