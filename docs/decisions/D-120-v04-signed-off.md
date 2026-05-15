---
id: D-120
title: CLIVE v0.4 signed off — all seven criteria met 15 May 2026
status: Accepted
date: 2026-05-15
blocks: All blocks
agents: All agents
---

## Context
D-113 and D-116 defined seven acceptance criteria for CLIVE v0.4.

## Decision
CLIVE v0.4 is signed off. All seven criteria are simultaneously true:

1. CI unit tests pass, including new tests for /list, /status, mobile ingest,
   and conversation memory. No test skipped or suppressed.

2. Mobile ingest works: sending a document without /ingest caption produces
   a prompt; /ingest_confirm completes the ingest. (D-114)

3. Desktop ingest (file + /ingest caption) continues to work unchanged.
   E2E test suite confirms v0.3 functionality not regressed.

4. /list returns a formatted list of ingested documents with filename, chunk
   count, and ingest date. Returns a clear empty message when the knowledge
   base is empty. Markdown removed from response to prevent parse failures
   on filenames containing underscores.

5. E2E test suite (D-106 criteria C2–C6) passes on every deploy in ~10s.

6. Conversation memory active: conversation_turns table populated on each
   query/response cycle; Block 8 receives history on every query. (D-115)

7. /status returns document count, chunk count, last ingest, last query date.
   Handles empty state gracefully.

Also shipped during v0.4 window (not in original criteria but live):
  D-117 — Block 25 observability stack (Prometheus, Loki, Grafana)
  D-118 — Block 25 alert routing via orchestrator webhook
  D-119 — Telegram /help command

## Bug fixed
Markdown parse failure in /list and /status: filenames with underscores
caused Telegram's Markdown v1 parser to throw BadRequest, silently dropping
the reply. Fixed by removing parse_mode="Markdown" from both handlers.

## Consequences
v0.4 is live. v0.5 scope to be defined by the owner. D-111 (mobile ingest
bug) is resolved and closed by D-114. Block 21 remains paused.
