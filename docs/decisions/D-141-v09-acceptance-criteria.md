---
id: D-141
title: CLIVE v0.9 acceptance criteria — nine criteria for Block 10 and Block 12 delivery
status: Accepted
date: 2026-05-17
blocks: Block 10, Block 12, Block 13, Block 8, Block 9, Block 16, Block 23, Block 25, Block 28
agents: Architect
---

## Context

v0.9 scope is defined in D-140. Nine acceptance criteria govern sign-off.
All nine must be simultaneously true before v0.9 is signed off.

## Options Considered

Not applicable — owner-directed acceptance criteria.

## Decision

CLIVE v0.9 is signed off when all nine criteria are simultaneously true:

**AC-1 — Worker schema in PostgreSQL**
`workers` table exists in `clive_state` with: FK to `tool_registry`
(`tool_name`), `schedule_type`, `cron_expression`, `trigger_event`,
`execution_scope` (TEXT[]), `last_run_at`. `worker_runs` table exists with:
`run_id` (PK), `worker_name`, `triggered_at`, `completed_at`, `status`,
`outcome_summary`, `error_detail`. Both `daily_digest` and
`knowledge_maintenance` are registered as rows in both `tool_registry` and
`workers` tables before first execution.

**AC-2 — Block 13 scheduler**
The orchestrator starts a scheduler at startup. The scheduler loads worker
schedules from the `workers` table in the database. It triggers `daily_digest`
at 08:00 UTC daily (`0 8 * * *`) and `knowledge_maintenance` at 09:00 UTC
every Monday (`0 9 * * 1`). Scheduler start is logged at INFO.

**AC-3 — Scope enforcement**
Workers receive a scoped capability dict limited to their declared
`execution_scope`. Block 13 logs a WARN and skips any capability call
attempted outside that scope. Scope enforcement is tested in the CI suite.

**AC-4 — Worker observability**
Worker outcomes are logged to `clive_state.worker_runs` on every run
(success or failure). A Prometheus counter `clive_worker_runs_total` with
labels `{worker_name, status}` is emitted per run. A Grafana panel is added
to the existing dashboard showing run history by worker and status.

**AC-5 — daily_digest worker**
The daily_digest worker runs on its cron schedule. It queries last-24h data:
query count, confirmed actions, LLM spend, feedback count, system health
(container status or equivalent). It formats a readable summary and delivers
it via the Telegram /alert endpoint. Failure is non-fatal — logged to
`worker_runs` with status `failed`; no retry loop; next scheduled run
proceeds normally.

**AC-6 — knowledge_maintenance worker**
The knowledge_maintenance worker runs weekly. It queries `clive_state` for
chunks where `retrieval_count = 0` AND `created_at` is older than the
configured threshold (default: 90 days). It presents up to 5 matching chunks
per run as a single batch to the owner via Block 9 confirmation gate
(`action_type = 'knowledge.prune'`). No autonomous deletion. D-006 applies.
`handle_prune_confirmed` deletes the identified chunks only after owner
confirms. If fewer than 5 stale chunks exist, it presents however many exist.
If zero stale chunks exist, it logs to `worker_runs` with
`outcome_summary = 'no stale chunks found'` and exits cleanly.

**AC-7 — Block 8 retrieval tracking**
Block 8 increments `retrieval_count` and sets `last_retrieved_at` on all
chunks returned in a successful query response. This operation is non-fatal:
wrapped in `try/except`; failure is logged at WARN but does not fail the
query response.

**AC-8 — Block 12 closed**
A policy document exists at `docs/spec/Block 12 - Context Window Policy.md`.
The document captures all context window policy: token budget, priority
ordering of context slots (personality, alignment, memory, RAG, conversation
history), minimum and maximum token allocations, and truncation strategy.
`context.py` in the Block 8 service declares all policy parameters as named
constants (not magic numbers) and references the policy document path in its
module docstring.

**AC-9 — CI passes**
All test suites pass: Block 13 scheduler tests (worker load, trigger
dispatch, scope enforcement), Block 8 retrieval tracking tests, knowledge
maintenance confirmation flow test, SQL init files are idempotent. No
regressions in existing test suites.

## Consequences

- v0.9 delivers the first proactive behaviour in CLIVE — daily_digest is the
  first time CLIVE acts without being directly prompted.
- knowledge_maintenance closes the loop between Block 8 retrieval tracking
  (AC-7) and Block 16 pruning — stale knowledge is surfaced to the owner
  safely and under D-006 constraint.
- Block 12 is formally closed. Context window policy is documented and
  constants are named. No future implementation should use magic numbers for
  token budgets.
- The workers table and scope enforcement pattern provide the runtime
  infrastructure for all future Block 10 workers.

## Related Decisions

- D-140 — v0.9 scope
- D-006 — confirmation gate (AC-6)
- D-003 — event bus principle (all worker comms via Block 13)
- D-044 — Block 8 dynamic context allocation (Block 12 partial, closed by AC-8)
- D-017 — tool registry as prerequisite for worker registration (AC-1)
