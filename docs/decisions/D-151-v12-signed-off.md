---
id: D-151
title: CLIVE v0.12 signed off — all ten criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 8, Block 10, Block 13, Block 19, Block 23, Block 28, Block 29
agents: Architect
---

## Context

D-149 approved v0.12 scope (Config/Admin complete + CLIVE Self-Knowledge).
D-150 defined ten acceptance criteria. This decision records sign-off.

## Verification

All ten D-150 acceptance criteria verified:

**AC-1 — Documents queryable conversationally**
`_detect_self_knowledge_intent()` in `src/query/query/handler.py` detects "documents"
intent and calls `/retrieve/document-list` via orchestrator. Vector RAG is bypassed.
`/list` command unchanged.

**AC-2 — Tools queryable conversationally**
Tools intent routes to `registry.get_tools()` (TTL-cached). Response formatted as
natural language prose. `/tools` command unchanged.

**AC-3 — Actions queryable conversationally**
New `/retrieve/action-history` orchestrator endpoint implemented in
`src/orchestrator/orchestrator/health.py` and `retrieval.py` as `retrieve_action_history()`.
Returns last 7 days of actions from `clive_state.pending_actions`.

**AC-4 — System health queryable conversationally**
Health/status intent routes to `/retrieve/status` (existing endpoint). Returns spend,
cap, document count, last ingest, last query. `/status` command unchanged.

**AC-5 — Spend cap configurable conversationally**
`_detect_spend_cap_intent()` detects "set daily cap to $N" patterns and emits
`action.pending` with action_type `config.set_spend_cap`. After confirmation:
`config_handler.handle_config_set_spend_cap()` upserts `daily_spend_cap_usd` in
`clive_state.config`. `spend.get_daily_cap()` reads config table first, falls back
to `DAILY_SPEND_CAP_USD` env var.

**AC-6 — Worker schedules configurable conversationally**
`worker.reschedule` action type implemented in `config_handler.handle_worker_reschedule()`.
After confirmation: `cron_expression` in `clive_state.workers` is updated. Worker
scheduler in Block 10 reads cron from DB at each tick.

**AC-7 — Config changes are audited**
`_write_audit()` in `config_handler.py` appends to `clive_state.audit_log` on every
config change. `config.changed` event emitted to Block 13 event bus after each change.
`changed_by = 'owner'` recorded in all entries. Survives process restart (DB-backed).

**AC-8 — Block 19 formally closed**
`clive_state.config` table created by `22_v12_config_table.sql` (idempotent — `CREATE
TABLE IF NOT EXISTS`, GRANT). Conversational config works end-to-end through Telegram.
Block 19 is marked Done in this decision.

**AC-9 — Block 29 formally closed**
All four self-knowledge intents (documents, tools, actions, health) return correct
live-state answers conversationally. Tests in `test_v12_self_knowledge.py` verify
detection and response path for each intent. Block 29 is marked Done in this decision.

**AC-10 — CI passes**
- `22_v12_config_table.sql` uses `CREATE TABLE IF NOT EXISTS` and GRANT patterns.
- `test_v12_config.py`: tests for `retrieve_action_history()` and `retrieve_workers()`
  including pool-not-initialised guards, unknown zone, and populated DB cases.
- `test_v12_self_knowledge.py`: tests for `_detect_self_knowledge_intent()` across all
  five intents, `_detect_spend_cap_intent()`, handle_query documents path, and spend cap
  action.pending path.
- `test_spend_cap.py`: extended to test config-table-first lookup (`get_daily_cap_prefers_config_over_env`).
- All pre-existing tests unchanged.

## Decision

v0.12 is signed off. All ten acceptance criteria met.

**Blocks formally closed by this version:**
- Block 19 (Config/Admin) — conversational config via Block 9 gate; `clive_state.config` table; audit trail
- Block 29 (Documentation) — CLIVE can describe its own state accurately via conversational queries

## Consequences

All partial blocks from the v1 roadmap are now formally closed:
- Block 3 closed at v0.11 (D-148)
- Block 4 closed at v0.11 (D-148)
- Block 5 closed at v0.11 (D-148)
- Block 12 closed at v0.9 (D-142)
- Block 19 closed at v0.12 (this decision)
- Block 29 closed at v0.12 (this decision)

Next version: v1.0 — Hardening + Block 24 Stub. Scope and acceptance criteria require
owner approval before implementation begins (D-008).

## Related Decisions

- D-149 — v0.12 scope
- D-150 — v0.12 acceptance criteria
- D-003 — Event bus (self-knowledge queries via orchestrator, not direct DB)
- D-006 — Confirmation gate (all config changes confirmed before execution)
- D-067 — Append-only audit log (config changes recorded)
