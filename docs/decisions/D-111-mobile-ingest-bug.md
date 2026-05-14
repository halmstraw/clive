---
id: D-111
title: Bug — /ingest caption command fails on Telegram mobile; fix deferred to v0.4
status: Accepted
date: 2026-05-14
blocks: Block 23, Block 14
agents: Experience Agent
---

## Context
D-101 defined the /ingest UX as: owner sends a document with `/ingest` as
the caption. This works on Telegram desktop (caption and file in one message).

On the Telegram mobile app, it is not possible to set an arbitrary caption
on a document before sending — the caption flow is either absent or too
constrained to type a slash command reliably.

## Decision
This is a confirmed bug against D-101. Fix is deferred to v0.4.

The Experience Agent must design an alternative ingest interaction pattern
that works on both desktop and mobile before v0.4 ships.

Candidate approaches (not decided here — Experience Agent owns the design):
  A. `/ingest` as a standalone command after sending a file — two messages
     with session state to correlate them.
  B. Bot auto-detects any document the owner sends and ingests it, asking
     for confirmation if needed.
  C. Bot presents an inline keyboard after any document is received, with
     an "Ingest" button.

The fix must not break the desktop flow (D-101 pattern still works there).

## Consequences
Ingest is currently desktop-only. Owner must use desktop Telegram to ingest
documents until v0.4. No workaround is available on mobile.

v0.4 cannot ship without this fixed and verified on mobile.

## Related Decisions
D-101 (ingest caption command — the decision this bug is against)
D-109 (deletion command, for comparison — /delete works on mobile as a
standalone text command with no file attachment required)
