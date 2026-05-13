---
id: D-103
title: CLIVE v0.2 acceptance criteria defined
status: Accepted
date: 2026-05-13
blocks: All blocks
agents: All agents
---

## Context
D-099 defined v0.2 scope but left "done" undefined. Without explicit
acceptance criteria, v0.2 ships by feel rather than by verified conditions.
D-080 established the precedent of naming criteria before implementation begins.

## Options Considered
Options not explicitly recorded — the requirement to define acceptance criteria
before implementation is governed by D-008 and the D-080 precedent.

## Decision
CLIVE v0.2 is shippable when all six criteria are simultaneously true:

1. All CI tests pass, including the new processing service tests for Block 15
   (chunking, embedding, chunk write). No test may be skipped or suppressed.

2. Sending a supported file to the Telegram bot with the caption `/ingest`
   causes the raw file to appear in the MinIO `clive-raw` bucket under the
   correct key. This is verifiable by querying MinIO directly or inspecting
   pipeline logs.

3. The Block 15 processing pipeline completes end-to-end for that file:
   chunks, embeddings, and metadata (source_key, content_hash, content_tsv)
   are written to `clive_search.chunks`. Verifiable via direct database query
   against the containerised test PostgreSQL instance and confirmed in
   production by log inspection.

4. A processed document is retrievable in a subsequent CLIVE query. The owner
   sends a question whose answer appears only in the ingested document; CLIVE
   returns a grounded response citing that document as a source.

5. Submitting a file over 10 MB via /ingest causes CLIVE to reply to the owner
   in Telegram with the rejection message defined in D-098, and no raw file is
   written to MinIO. An `ingest.rejected` event appears in the audit log.

6. The audit log records `ingest.processed` for a successful ingestion and
   `ingest.rejected` for an oversized-file rejection. Both events include
   full provenance (source_key, file size, timestamp, owner chat ID).

## Rationale
Criteria 1–3 verify the pipeline works in isolation (CI and direct DB
inspection). Criterion 4 is the end-to-end proof that the system actually
knows what was ingested. Criterion 5 enforces the D-098 size gate from the
owner's perspective, not just at the pipeline level. Criterion 6 ensures the
audit trail covers both ingestion paths, consistent with D-067 (append-only
audit log). All six must be true simultaneously.

## Consequences
v0.2 cannot be signed off without a demonstrated end-to-end retrieval (criterion 4),
not merely a passing CI suite. Rules out shipping v0.2 on pipeline pass alone.
T8 (data deletion) and Block 18 (Feedback/Correction) remain out of v0.2 scope
per D-100. FLAG-3 (Telegram /ingest interaction pattern) was resolved at D-101
(caption command pattern) and does not block these criteria.

## Related Decisions
D-080 (v0.1 acceptance criteria), D-094 (v0.1 signed off), D-095 (CI uses
containerised PostgreSQL), D-096 (embedding model), D-097 (chunking parameters),
D-098 (10 MB size limit), D-099 (v0.2 scope), D-100 (Block 18 deferred),
D-101 (Telegram /ingest caption pattern).
