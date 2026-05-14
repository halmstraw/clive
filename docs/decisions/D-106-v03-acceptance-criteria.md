---
id: D-106
title: CLIVE v0.3 acceptance criteria defined
status: Accepted
date: 2026-05-14
blocks: Block 9, Block 14, Block 15, Block 16, Block 18, Block 23, Block 28
agents: All agents
---

## Context
D-105 defined v0.3 scope (T8 data deletion + Block 18 Feedback) but left
"done" undefined. The D-080/D-103 precedent requires explicit, verifiable
acceptance criteria before implementation begins.

## Options Considered
Options not explicitly recorded — the requirement to define acceptance criteria
before implementation is governed by D-008 and the D-080/D-103 precedent.

## Decision
CLIVE v0.3 is shippable when all six criteria are simultaneously true:

1. All CI tests pass, including new tests for Block 9 (confirmation gate),
   the deletion flow (Block 14/15/16), and Block 18 (feedback). No test may
   be skipped or suppressed.

2. Sending a deletion request for a previously ingested document causes CLIVE
   to ask for explicit confirmation before taking action. Without confirmation,
   or on explicit rejection, no deletion occurs and no data is changed.
   (D-006 compliance verified from the owner's perspective.)

3. After the owner confirms a deletion: all chunks for that document are
   removed from clive_search.chunks, the raw file is removed from the MinIO
   clive-raw bucket, and the document is no longer retrievable in a subsequent
   CLIVE query whose answer appears only in that document. Verifiable by
   direct database query and log inspection.

4. Sending a deletion request for a document that does not exist causes CLIVE
   to reply with a clear "not found" message. No crash, no unhandled error.

5. The owner can tag the most recent retrieval as poor quality via a single
   Telegram command. CLIVE acknowledges. The feedback is persisted in storage.
   Verifiable by direct database query.

6. The audit log records: deletion requests, confirmed deletions, deletion
   cancellations, and feedback events — all with full provenance (document
   identifier, timestamp, owner chat ID). Consistent with D-067
   (append-only audit log).

## Open Flag
FLAG-1 (non-blocking): the Telegram interaction pattern for deletion — how
the owner identifies which document to delete (by filename, by list selection,
etc.) — is unresolved. Must be resolved by the Experience Agent before
end-to-end deletion testing begins. Does not block Block 9 implementation
or the acceptance of these criteria. Analogous to FLAG-3 from v0.2,
resolved at D-101.

## Rationale
Criterion 1 verifies pipeline isolation (CI). Criterion 2 enforces the D-006
confirmation gate from the owner's perspective. Criterion 3 is the end-to-end
proof that deletion is complete — chunks, vectors, and raw file. Criterion 4
covers the failure case. Criterion 5 verifies Block 18 end-to-end. Criterion 6
ensures the audit trail covers all new event types, consistent with D-067.
All six must be true simultaneously.

## Consequences
v0.3 cannot be signed off without a demonstrated end-to-end deletion including
confirmed non-retrievability (criterion 3) and a demonstrated feedback
persistence (criterion 5). Rules out shipping on CI pass alone. FLAG-1
(deletion interaction pattern) must be resolved by Experience Agent before
end-to-end testing; Knowledge Agent and Intelligence Agent work is not blocked
by it. Block 21 (Evolution Engine) remains paused. Business Layer remains out
of scope per D-036.

## Related Decisions
D-006 (confirmation gate), D-067 (append-only audit log), D-080 (v0.1
criteria), D-094 (v0.1 signed off), D-099 (v0.2 scope), D-100 (Block 18
deferred to v0.3), D-103 (v0.2 criteria), D-104 (v0.2 signed off),
D-105 (v0.3 scope).
