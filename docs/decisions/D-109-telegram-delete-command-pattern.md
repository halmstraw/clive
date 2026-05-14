---
id: D-109
title: Telegram deletion command uses /delete <filename> — direct single-step pattern
status: Accepted
date: 2026-05-14
blocks: Block 23, Block 4, Block 9, Block 14, Block 16
agents: Experience Agent, Knowledge Agent, Intelligence Agent
---

## Context
FLAG-1 from D-106: the Telegram interaction pattern for T8 (document deletion) was
unresolved. Needed to be decided before end-to-end deletion testing could begin.
Three options were evaluated by the Experience Agent and put to the owner.

## Options Considered
A. Direct command with filename: /delete <filename> (e.g. /delete report.pdf).
   Single step. Owner must know the filename. Consistent with D-101 caption pattern.
B. List then select: /list first, then /delete <number>. Two steps, discovery-friendly.
C. Re-upload to identify: owner re-sends the file; CLIVE matches by filename/hash.

## Decision
Option A. Owner approved 2026-05-14.

/delete <filename> — single-step direct command.

The source_key stored in clive_search.chunks is in the format {uuid}/{original_filename}.
Deletion lookup uses: WHERE source_key LIKE '%/' || $1, matching on the original filename
suffix. If multiple documents share the same filename, all matching source_keys are
presented in the confirmation message so the owner knows what will be deleted.

If no match: CLIVE replies "No document named {filename} found." — clean not-found path.

Confirmation gate (Block 9, D-006): after the lookup succeeds, CLIVE asks for explicit
confirmation before any deletion executes. The owner replies /confirm_delete to proceed
or /cancel_delete to abort. Timeout equals rejection (D-006).

## Rationale
Consistent with the D-101 caption command pattern — direct, single-step, no stateful
discovery round-trip. The filename is the natural identifier for documents the owner
has ingested. The UUID prefix is internal; it does not appear in owner-facing messages.

## Consequences
- Block 9 confirmation message must show the human-readable filename, not the raw source_key.
- The /confirm_delete and /cancel_delete commands must be registered in the Telegram bot.
- Multiple documents with the same filename are handled: confirmation shows all matching
  source_keys; all are deleted on confirmation.
- D-106 criterion 4 (not-found → clear message, no crash) is the explicit failure path.

## Related Decisions
D-006 (confirmation gate), D-101 (ingest caption pattern), D-105 (v0.3 scope),
D-106 (v0.3 acceptance criteria).
