---
id: D-149
title: CLIVE v0.12 scope — Config/Admin complete + CLIVE Self-Knowledge
status: Accepted
date: 2026-05-17
blocks: Block 8, Block 10, Block 13, Block 19, Block 23, Block 28, Block 29
agents: Architect, Intelligence Agent, Systems Agent
---

## Context

v0.11 is in progress (D-146, D-147). D-148 will record v0.11 sign-off when complete.

v0.12 is next per the roadmap. Theme: close all remaining partial blocks. By v0.12
a tool registry, workers, two surfaces, and users/zones are all in place. The control
plane now has something worth controlling, and Block 10 workers provide the operational
state CLIVE needs to answer questions about itself.

## Decision

v0.12 scope is approved. Theme: the owner can configure CLIVE conversationally, and
CLIVE can describe itself accurately.

**Primary blocks:** 19 (completes partial), 29 (closes partial)

**Block 29 — Self-Knowledge:**
Block 8 gains a self-knowledge detection path, parallel to the existing action-intent
path. Detected introspective queries short-circuit the full RAG pipeline and call
orchestrator state endpoints directly (D-043).

Self-knowledge intents and their data sources:
- "documents" / "what do you know" → `/retrieve/document-list` (already exists)
- "tools" / "what can you do" → live tool_registry via `registry.get_tools()` (already cached)
- "actions" / "what did you do" → new `/retrieve/action-history` endpoint (recent
  confirmed/rejected actions from `clive_state.pending_actions`)
- "workers" / "background tasks" → new `/retrieve/workers` endpoint (tool_registry
  entries where tool_type = 'worker')
- "status" / "health" / "cost" / "spend" → `/retrieve/status` (already returns spend data)

Block 8's `_detect_self_knowledge_intent()` uses phrase matching (similar to
`_detect_action_intent()`). Self-knowledge responses are formatted as natural language
prose by Block 8 before emitting `query.response`. The existing `/list`, `/tools`,
`/status` commands are unchanged — they remain the structured command interface.

**Block 19 — Conversational Config:**
A new `clive_state.config` table stores runtime configuration values as typed key/value
pairs with timestamps and version tracking. This becomes the runtime source for
owner-adjustable values; env vars remain as bootstrap fallback.

Owner-adjustable config values in v0.12 scope:
- `daily_spend_cap_usd` — replaces DAILY_SPEND_CAP_USD env var as the live source;
  Block 20 spend cap check reads `clive_state.config` first, falls back to env var
- Worker schedules — cron expression per registered worker, stored in
  `clive_state.tool_registry` and updated by the `worker.reschedule` action type

Conversational config changes detected by Block 8 route through Block 9 confirmation
gate (D-006) as new action types:
- `config.set_spend_cap` — sets `daily_spend_cap_usd` in `clive_state.config`
- `worker.reschedule` — updates the schedule field for a named worker in
  `clive_state.tool_registry`

All config changes emit `config.changed` (already established from `handle_confirm_activate`)
and are recorded in `clive_state.audit_log`.

## Consequences

- New `_detect_self_knowledge_intent()` and `_handle_self_knowledge_query()` in
  `src/query/query/handler.py` — self-knowledge path inserted before vector RAG
- New retrieval functions in `src/orchestrator/orchestrator/retrieval.py`:
  `retrieve_action_history()` and `retrieve_workers()`
- New HTTP routes in orchestrator `main.py`: `/retrieve/action-history`,
  `/retrieve/workers`
- New SQL init script: `22_v12_config_table.sql` — `clive_state.config` table
- Block 9 action handler extended with `config.set_spend_cap` and `worker.reschedule`
- Block 20 spend cap lookup extended: reads `clive_state.config` before env var
- Block 19 formally closed
- Block 29 formally closed

## Related Decisions

- D-140 — v0.9 scope (Block 10 workers — v0.12 builds on worker registry)
- D-146 — v0.11 scope (prerequisite; v0.12 Telegram work is v0.11-independent)
- D-003 — Event bus (self-knowledge queries via orchestrator endpoints, not direct DB)
- D-006 — Confirmation gate (all config changes require explicit owner confirmation)
- D-025 — At-least-once delivery (config change handlers must be idempotent)
- D-043 — Orchestrator-mediated retrieval (self-knowledge uses the established pattern)
- D-067 — Append-only audit log (config changes recorded here)
