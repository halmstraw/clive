---
id: D-105
title: CLIVE v0.3 scope approved
status: Accepted
date: 2026-05-14
blocks: Block 9, Block 14, Block 15, Block 16, Block 18, Block 23
agents: All agents
---

## Context
CLIVE v0.2 was signed off (D-104, 14 May 2026). The owner can now ingest
documents via Telegram and query them. Two items were explicitly deferred from
v0.2: T8 (data deletion, D-099) and Block 18 (Feedback/Correction, D-100).
Both are now the primary candidates for v0.3.

## Options Considered
A. Narrow — T8 (data deletion) only.
B. Moderate — T8 + Block 18 (Feedback). Both deferred items together.
C. Broad — T8 + Block 18 + Terraform GHA secret name fix as formal criterion.

## Decision
Option B selected. CLIVE v0.3 delivers:

**T8 — Data deletion**
Owner can delete a previously ingested document from CLIVE's knowledge via
Telegram. Deletion is irreversible and therefore requires the Block 9
(Action Layer) confirmation gate per D-006. On confirmed deletion: all chunks
for the document are removed from clive_search.chunks, the raw file is removed
from the MinIO clive-raw bucket, and the document is no longer retrievable.

Block 9 (Action Layer) is a prerequisite for T8 and is in v0.3 scope as the
enabling infrastructure.

**Block 18 — Feedback/Correction**
Owner can tag the most recent retrieval as poor quality via a single Telegram
command. Feedback is persisted. No Evolution Engine dependency required for
this initial implementation.

## Rationale
T8 is the most pressing gap: the owner can put documents in but cannot remove
them. Block 18 is small (one command), was designed and deferred from v0.2,
and completes a coherent "manage what CLIVE knows" release. Both together make
v0.3 a meaningful capability step without pulling in deferred scope (Block 17,
Block 21, Blocks 30–38).

The Terraform GHA secret name mismatch (HCLOUD_TOKEN vs HETZNER_API_TOKEN)
is a maintenance fix that should be applied immediately; it does not warrant
formal scope inclusion.

## Consequences
v0.3 work may begin once acceptance criteria are recorded (D-106). Block 9 must
be implemented before T8 can be wired end-to-end. Block 21 (Evolution Engine)
remains paused. Business Layer (Blocks 30–38) remains out of scope per D-036.
The deletion interaction pattern (how the owner identifies and initiates a
deletion via Telegram) is an open UX question — FLAG-1 for this session, to
be resolved by the Experience Agent before end-to-end deletion testing begins.

## Related Decisions
D-006 (confirmation gate), D-094 (v0.1 signed off), D-099 (v0.2 scope),
D-100 (Block 18 deferred to v0.3), D-104 (v0.2 signed off).
