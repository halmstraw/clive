---
id: D-104
title: CLIVE v0.2 signed off; all six criteria met 14 May 2026
status: Accepted
date: 2026-05-14
blocks: All blocks
agents: All agents
---

## Context
D-103 defined six criteria that must be met before CLIVE v0.2 can be
considered complete. All six criteria required owner sign-off.

## Options Considered
Not applicable — sign-off is a binary confirmation by the owner.

## Decision
CLIVE v0.2 is signed off as complete. All six criteria defined in D-103 are
met as of 14 May 2026:

1. All CI tests pass, including Block 15 processing service tests.
2. Sending a file via /ingest causes the raw file to appear in the MinIO
   clive-raw-store bucket under the correct key.
3. The Block 15 processing pipeline completes end-to-end: 1 chunk stored
   in clive_search.chunks with source_key, content_hash, and content_tsv.
4. Ingested document retrievable in a subsequent CLIVE query. Question:
   "What is the budget for NIGHTJAR-7?" Answer: "47,200 units." — correct,
   grounded in the ingested document, not general knowledge.
5. Sending a file over 10 MB via /ingest causes CLIVE to reply "File too
   large (11 MB). Maximum is 10 MB." No raw file written to MinIO.
6. Audit log records ingest.processed (2026-05-14 08:15:38) and
   ingest.rejected (2026-05-14 08:23:42) with timestamps and
   conversation IDs.

## Rationale
All six D-103 criteria confirmed met by end-to-end production verification.
Owner sign-off given 14 May 2026.

## Consequences
v0.2 is closed. CLIVE can now ingest documents via Telegram and answer
questions grounded in those documents. T8 (data deletion) and Block 18
(Feedback/Correction) remain deferred to v0.3 per D-100. v0.3 scope to
be defined before work begins.

## Related Decisions
D-099 (v0.2 scope), D-103 (v0.2 acceptance criteria), D-100 (Block 18
and T8 deferred to v0.3).
