---
id: D-114
title: Mobile ingest uses document-received trigger with /ingest_confirm command
status: Accepted
date: 2026-05-14
blocks: Block 23, Block 14
agents: Experience Agent
---

## Context
D-111 records that the /ingest caption command (D-101) cannot be used on
Telegram mobile because the mobile app does not support typing a slash
command as a document caption before sending.

## Decision
Replace D-101 single-step pattern with a two-step pattern for mobile:

  Step 1: Owner sends a document with any caption OTHER than /ingest,
          or with no caption at all. Bot stores pending ingest state
          (file_id, original_filename, file_size, mime_type) in memory
          and replies: "Ingest [filename]? Send /ingest_confirm to proceed."

  Step 2: Owner sends /ingest_confirm. Bot downloads the file using the
          stored file_id, uploads to MinIO, emits ingest.received to
          Block 13, and acknowledges.

The D-101 desktop pattern is unchanged and continues to work:
  Owner sends document WITH /ingest caption → ingest proceeds immediately
  (no confirmation prompt, same as v0.1/v0.2/v0.3 behaviour).

Session state: _pending_ingests dict in Block 23 process memory, keyed by
chat_id. Sending a second document before confirming overwrites the pending
state (the newer document takes priority). No persistence across restarts —
owner must re-send the file if the bot restarts.

## Consequences
Both mobile and desktop ingest work. /ingest_confirm is a new command
registered in Block 23. The existing /ingest caption handler is unchanged.
D-113 criterion 2 and 3 are the acceptance tests for this decision.
