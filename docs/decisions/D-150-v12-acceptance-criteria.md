---
id: D-150
title: CLIVE v0.12 acceptance criteria — ten criteria for Config/Admin + Self-Knowledge
status: Accepted
date: 2026-05-17
blocks: Block 8, Block 10, Block 13, Block 19, Block 23, Block 28, Block 29
agents: Architect
---

## Context

D-149 defines v0.12 scope. Acceptance criteria must be recorded before implementation
begins (D-008).

## Decision

v0.12 is done when ALL of the following are simultaneously true:

**AC-1 — Documents queryable conversationally**
Sending "what documents do you know about?" (or equivalent phrasing) returns a natural
language list of ingested documents from live `clive_search.chunks` state. Block 8
detects the intent via `_detect_self_knowledge_intent()` and calls
`/retrieve/document-list` via the orchestrator. Vector RAG is not invoked. The `/list`
command continues to function unchanged.

**AC-2 — Tools queryable conversationally**
Sending "what tools do you have?" (or equivalent) returns a natural language description
of available tools from the live tool registry. Block 8 uses `registry.get_tools()`
(already TTL-cached). Response is formatted as readable prose. The `/tools` command
continues to function unchanged.

**AC-3 — Actions queryable conversationally**
Sending "what actions did you take this week?" (or equivalent) returns a natural
language summary of recent confirmed and rejected actions. New `/retrieve/action-history`
orchestrator endpoint returns the last 7 days of actions from `clive_state.pending_actions`
with action_type, action_target, status, and created_at.

**AC-4 — System health queryable conversationally**
Sending "how much have you cost today?" or "what's your system status?" (or equivalent)
returns a natural language health summary: LLM spend, daily cap if set, document count,
last ingest, and last query time. Block 8 calls `/retrieve/status` (already returns
this data). The `/status` command continues to function unchanged.

**AC-5 — Spend cap configurable conversationally**
Sending "set my daily spend cap to $5" (or equivalent) routes through Block 9
confirmation gate as action type `config.set_spend_cap`. On confirmation:
`daily_spend_cap_usd` is written to `clive_state.config`. Block 20 spend cap check
reads `clive_state.config` before falling back to the `DAILY_SPEND_CAP_USD` env var.
On cancellation: config is unchanged.

**AC-6 — Worker schedules configurable conversationally**
Sending "run the daily digest at 9am" (or equivalent) routes through Block 9
confirmation gate as action type `worker.reschedule`. On confirmation: the schedule
field for the named worker is updated in `clive_state.tool_registry`. Worker schedules
stored in `clive_state.tool_registry` take precedence over default schedules at
execution time.

**AC-7 — Config changes are audited**
All config changes (spend cap, worker schedule) emit `config.changed` to Block 13
and are recorded in `clive_state.audit_log` with change_type, old_value, new_value,
and changed_by = 'owner'. Record survives a process restart.

**AC-8 — Block 19 formally closed**
`clive_state.config` table exists (idempotent SQL in `22_v12_config_table.sql`).
Conversational config (AC-5, AC-6) works through Telegram. Block 19 is marked Done
in the decision log (D-151).

**AC-9 — Block 29 formally closed**
Self-knowledge queries for documents (AC-1), tools (AC-2), actions (AC-3), and health
(AC-4) all return correct live-state answers conversationally. Block 29 is marked Done
in the decision log (D-151).

**AC-10 — CI passes**
- SQL idempotency: `22_v12_config_table.sql` uses `CREATE TABLE IF NOT EXISTS`,
  `ON CONFLICT DO NOTHING`, and `GRANT` patterns consistent with other init scripts.
- `test-db` CI job: new step asserts `clive_state.config` table and expected columns
  exist.
- Unit tests exist for `_detect_self_knowledge_intent()`, `retrieve_action_history()`,
  and `retrieve_workers()`; all pass.
- All pre-existing tests pass unchanged.

## Consequences

Sign-off decision (D-151) records when all ten criteria are verified.

## Related Decisions

- D-149 — v0.12 scope
- D-003 — Event bus principle
- D-006 — Confirmation gate
- D-025 — At-least-once delivery
