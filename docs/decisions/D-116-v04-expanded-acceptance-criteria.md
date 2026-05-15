---
id: D-116
title: CLIVE v0.4 acceptance criteria extended — conversation memory and /status
status: Accepted
date: 2026-05-14
blocks: Block 8, Block 13, Block 16, Block 23, Block 28
agents: All agents
---

## Context
D-113 defined five acceptance criteria for v0.4. Owner approved expanded scope
to include conversation memory (D-115) and /status command.

## Decision
v0.4 acceptance criteria are extended to seven. D-113 criteria 1-5 stand.
Additional criteria:

6. Conversation memory active: after asking CLIVE two questions in a row,
   the second response demonstrates awareness of the first exchange
   (references it or uses it as context). Verifiable by direct interaction.

7. /status returns a formatted summary: document count, chunk count, last
   ingest filename and date, last query date. Returns gracefully when the
   knowledge base is empty or no queries have been made yet.

All seven criteria must be simultaneously true for v0.4 sign-off.

## Consequences
v0.4 cannot ship without criteria 6 and 7 verified alongside 1-5.
