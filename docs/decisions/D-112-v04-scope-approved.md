---
id: D-112
title: CLIVE v0.4 scope approved — mobile ingest fix + /list command
status: Accepted
date: 2026-05-14
blocks: Block 23, Block 14, Block 16
agents: Experience Agent, Knowledge Agent
---

## Context
v0.3 shipped and is live (D-110, 14 May 2026). D-111 records a known bug:
the /ingest caption command (D-101) does not work on Telegram mobile.
There is also no command to list ingested documents.

## Decision
v0.4 delivers two items:

1. Mobile ingest fix (D-111) — Block 23.
   Any document received from the owner without an /ingest caption triggers
   an ingest prompt. The owner sends /ingest_confirm to complete the ingest.
   Desktop caption flow (D-101) is unchanged.
   UX design recorded in D-114.

2. /list command — Block 23 + Block 16.
   New Telegram command /list shows all ingested documents: filename,
   chunk count, and ingest date. Returns a clear message when empty.
   Routed via orchestrator retrieval endpoint (D-043 pattern).

## Out of scope
Block 20 (cost monitoring), Block 11 (memory), Block 21 (Evolution Engine)
remain deferred. Node.js GHA warning folded into next infra commit.

## Consequences
v0.4 closes the mobile usability gap and gives the owner visibility into
their knowledge base. Both items are small and reversible via GitHub.
