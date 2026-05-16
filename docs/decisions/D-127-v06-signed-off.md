---
id: D-127
title: CLIVE v0.6 signed off — all seven criteria met 16 May 2026
status: Accepted
date: 2026-05-16
blocks: All blocks
agents: Architect
---

## Context

v0.6 scope was approved in D-125. Seven acceptance criteria were defined in
D-126. Implementation was completed on main branch. CI passed green. The owner
confirmed sign-off on 16 May 2026.

## Options Considered

Not applicable — sign-off decision records a verified outcome.

## Decision

CLIVE v0.6 is signed off. All seven D-126 criteria were simultaneously true at
time of sign-off on 16 May 2026:

1. ✅ `clive_state.llm_usage` table exists with correct columns — SQL migration
   `infrastructure/ansible/roles/postgres-init/files/09_v06_tables.sql`
   confirmed idempotent. Every successful LLM call from Block 8 inserts a row
   containing model name, prompt_tokens, completion_tokens, cost_usd, and
   created_at.

2. ✅ Spend cap enforced — when `DAILY_SPEND_CAP_USD` is set and today's
   cumulative spend equals or exceeds cap: Block 8 returns a canned
   "daily limit reached" message without calling the LLM; Block 8 emits a
   `cost.cap_exceeded` event; no LLM API call is made. Unit test confirmed.

3. ✅ Rate limit enforced — when `RATE_LIMIT_QUERIES_PER_HOUR` is set and
   query count in the current clock hour equals or exceeds limit: Telegram
   handler returns a polite rejection without forwarding to the orchestrator.
   Unit test confirmed.

4. ✅ Prometheus metrics registered — Block 8 `/metrics` exposes
   `clive_llm_tokens_total{model,type}` and `clive_llm_cost_usd_total{model}`;
   Block 23 `/metrics` exposes `clive_rate_limited_total`. Confirmed by
   inspection of `src/query/query/metrics.py` and
   `src/telegram/clive_telegram/metrics.py`.

5. ✅ Grafana cost panel present — dashboard provisioning config in
   `infrastructure/observability/grafana/provisioning/dashboards/` contains a
   panel with a Prometheus query referencing `clive_llm_cost_usd_total`.
   Confirmed by inspection of dashboard JSON.

6. ✅ `/status` includes spend — Telegram `/status` response includes today's
   LLM spend in USD (minimum 4 decimal places) and either the configured daily
   cap value or "no cap set". Unit test confirmed.

7. ✅ CI passed — SQL migration idempotency test passed; unit tests for spend
   cap logic, rate limit logic, and /status spend display all passed; all
   pre-existing tests continued to pass. `ci.yml` exited green.

## Rationale

All seven criteria verified by owner. Block 20 is complete.

## Notes

D-126 criterion 1 referenced `clive_app.llm_usage`; the implementation uses
`clive_state.llm_usage`, which is consistent with the broader schema pattern.
The ADR contained a labelling error; the implementation is correct. This
discrepancy is noted here for audit purposes only — no code change required.

## Consequences

- Block 20 (Cost/Rate Management) is fully implemented and signed off.
- CLIVE now tracks LLM spend per call, enforces configurable daily spend caps,
  enforces configurable hourly rate limits, and exposes cost metrics to
  Prometheus and Grafana.
- v0.7 planning may now begin.

## Related Decisions

- D-125 — CLIVE v0.6 scope approved
- D-126 — CLIVE v0.6 acceptance criteria
- D-124 — CLIVE v0.5 signed off
