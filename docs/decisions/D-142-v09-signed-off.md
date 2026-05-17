---
id: D-142
title: CLIVE v0.9 signed off — all nine criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 10, Block 12, Block 13, Block 8, Block 9, Block 16, Block 23, Block 25, Block 28
agents: Infrastructure Agent, Architect
---

## Context

D-141 defined nine acceptance criteria for v0.9. All nine were verified by
the Infrastructure Agent on 17 May 2026 before owner sign-off.

## Decision

CLIVE v0.9 is signed off. All nine D-141 acceptance criteria are simultaneously
true as of 17 May 2026.

AC-1 — Worker schema in PostgreSQL: `workers` and `worker_runs` tables created
and seeded (SQL init files 14+15, commit 49216c5). Both `daily_digest` and
`knowledge_maintenance` registered in `tool_registry` and `workers` before
first execution.

AC-2 — Block 13 scheduler: Scheduler starts at orchestrator boot, loads worker
schedules from DB, triggers `daily_digest` at `0 8 * * *` and
`knowledge_maintenance` at `0 9 * * 1`. Committed 05f7fa1.

AC-3 — Scope enforcement: `make_scoped_push` builds capability dict limited to
declared `execution_scope`. Five test assertions verified present in
`test_v09_scheduler.py`.

AC-4 — Worker observability: `worker_runs` table logs every run outcome.
`clive_worker_runs_total{worker_name, status}` Prometheus counter emitted per
run. Grafana stat panel "Worker Runs (24h)" added to event bus dashboard
(uid: clive-event-bus, commit ae6a46a).

AC-5 — daily_digest worker: Queries last-24h data across five sources, formats
readable summary, delivers via Telegram /alert endpoint. Failure non-fatal.
Committed 1dc323a. 14+ tests in `test_v09_daily_digest.py`.

AC-6 — knowledge_maintenance worker: Identifies chunks where
`retrieval_count = 0` AND `created_at` older than threshold (default 90 days).
Presents up to 5 per run via D-006 confirmation gate. No autonomous deletion.
`handle_prune_confirmed` deletes only after owner confirms. Committed 675ee1a.
14+ tests in `test_v09_knowledge_maintenance.py`.

AC-7 — Block 8 retrieval tracking: Block 8 increments `retrieval_count` and
sets `last_retrieved_at` on all chunks returned per query. Non-fatal: wrapped
in try/except. Committed d1357bc. 5 test assertions in
`test_v09_retrieval_tracking.py`.

AC-8 — Block 12 closed: `docs/spec/Block 12 - Context Window Policy.md`
exists. `context.py` module docstring references the policy document path.
All token budget values declared as named constants (TOTAL_BUDGET,
MIN_HISTORY_TOKENS, MIN_MEMORY_TOKENS, MIN_RETRIEVAL_TOKENS). No magic numbers.

AC-9 — CI passes: All three new SQL files idempotent (IF NOT EXISTS, ON
CONFLICT DO NOTHING throughout). CI glob covers files 14/15/16. `croniter>=2.0`
in orchestrator `pyproject.toml`. All required test assertions confirmed present
across four test files. No regressions in existing suites.

## Consequences

- v0.9 is in production. CLIVE now has proactive behaviour: daily_digest runs
  unsolicited at 08:00 UTC — the first time CLIVE acts without being prompted.
- knowledge_maintenance closes the Block 8 → Block 16 stale-knowledge loop
  under D-006 constraints.
- Block 12 is formally closed. All context window policy is documented and
  implemented as named constants.
- Worker table and scope enforcement pattern provide the runtime infrastructure
  for all future Block 10 workers.
- v0.10 scope (D-143) and acceptance criteria (D-144) are pre-staged and ready
  for the next sprint.

## Related Decisions

- D-140 — v0.9 scope
- D-141 — v0.9 acceptance criteria
- D-006 — confirmation gate (AC-6)
- D-003 — event bus principle
- D-134 — event bus observability dashboard (AC-4 Grafana panel)
