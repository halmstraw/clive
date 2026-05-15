---
id: D-113
title: CLIVE v0.4 acceptance criteria defined
status: Accepted
date: 2026-05-14
blocks: Block 23, Block 14, Block 16, Block 28
agents: All agents
---

## Context
D-112 approved v0.4 scope. D-008 requires explicit acceptance criteria
before implementation.

## Decision
CLIVE v0.4 is shippable when all five criteria are simultaneously true:

1. All CI tests pass, including new unit tests for /list and mobile ingest.
   No test may be skipped or suppressed.

2. Sending a document to the bot without an /ingest caption produces a
   prompt asking the owner to confirm. Sending /ingest_confirm after the
   prompt triggers ingest. The document is ingested and the owner receives
   a follow-up when processing completes. (Mobile and desktop.)

3. Sending a document with /ingest as the caption (D-101 desktop flow)
   continues to work unchanged. Both ingest paths produce the same outcome.

4. /list returns a formatted list of ingested documents with filename,
   chunk count, and ingest date. When no documents are ingested, returns
   a clear "nothing here" message without error.

5. The E2E test suite (D-106 criteria C2–C6) continues to pass on every
   deploy, confirming v0.3 functionality is not regressed.

## Consequences
v0.4 cannot ship unless all five criteria hold simultaneously.
