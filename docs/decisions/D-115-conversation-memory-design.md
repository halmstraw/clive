---
id: D-115
title: Conversation memory (Block 11 minimal) — store turns in DB, inject into Block 8 context
status: Accepted
date: 2026-05-14
blocks: Block 8, Block 13, Block 16
agents: Systems Agent, Knowledge Agent
---

## Context
Block 8's context assembler (context.py) already accepts conversation_history
as a list of {role, content} dicts and incorporates it into the LLM prompt
(D-044 Tier 3). However, Block 13's push_query_to_block8 was sending an empty
list — no history was ever populated.

## Decision
Store conversation turns in clive_state.conversation_turns (new table, 08_v04_tables.sql).
Block 13 mediates all memory operations (D-003):

  On query.received dispatch (push_query_to_block8):
    1. Fetch last CONVERSATION_HISTORY_LIMIT turns for conversation_id
    2. Pass as conversation_history in the payload to Block 8
    3. After successful push, store the user turn (idempotent, keyed on event_id + role)

  On query.response dispatch (push_response_to_surface):
    1. Push to Block 23 as before
    2. After successful push, store the assistant turn (idempotent)

Limit: CONVERSATION_HISTORY_LIMIT env var, default 10 turns (5 exchanges).
Memory functions live in retrieval.py (same DB pool, clive_app role).
Failures are logged and non-fatal — query proceeds without history.

## Consequences
CLIVE remembers recent exchanges within and across sessions.
No summarisation at v0.4 — oldest turns are simply omitted when limit is reached.
No cleanup/pruning at v0.4 — personal system, table growth is acceptable.
D-025 idempotency guaranteed by UNIQUE (event_id, role) constraint.
