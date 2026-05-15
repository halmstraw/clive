---
id: D-126
title: CLIVE v0.6 acceptance criteria defined
status: Accepted
date: 2026-05-15
blocks: Block 20 (Cost/Rate), Block 8 (Query), Block 13 (Orchestrator), Block 16 (Storage), Block 23 (Telegram), Block 25 (Observability), Block 28 (CI/CD)
agents: Intelligence Agent, Systems Agent, Knowledge Agent, Experience Agent, Infrastructure Agent
---

## Context

v0.6 scope is approved (D-125). Before implementation proceeds, acceptance
criteria must be defined so that "done" is unambiguous and sign-off can be
verified objectively. These criteria gate the v0.6 sign-off decision.

## Decision

All seven criteria must be simultaneously true for v0.6 sign-off:

1. **Usage table** — `clive_app.llm_usage` table exists (SQL migration
   idempotent). Every successful LLM call from Block 8 inserts a row
   containing at minimum: model name, prompt_tokens, completion_tokens,
   cost_usd (float), and created_at (timestamp). Verifiable by inspection of
   the SQL migration file and a unit test asserting the insert path is called.

2. **Spend cap enforced** — when `DAILY_SPEND_CAP_USD` is set and today's
   cumulative spend in `llm_usage` equals or exceeds the cap value: Block 8
   returns a canned "daily limit reached" message without calling the LLM;
   Block 8 emits a `cost.cap_exceeded` event; no LLM API call is made.
   Verifiable by unit test with mocked DB spend and mocked LLM client.

3. **Rate limit enforced** — when `RATE_LIMIT_QUERIES_PER_HOUR` is set and
   the query count in the current clock hour equals or exceeds the limit: the
   Telegram handler returns a polite rejection message without forwarding the
   query to the orchestrator. Verifiable by unit test.

4. **Prometheus metrics** — Block 8's `/metrics` endpoint exposes
   `clive_llm_tokens_total` (labelled by model and type=prompt|completion) and
   `clive_llm_cost_usd_total` (labelled by model). Block 23's `/metrics`
   endpoint exposes `clive_rate_limited_total`. Verifiable by inspection of
   source code metric registration and the existing Prometheus scrape config
   targeting those endpoints.

5. **Grafana cost panel** — the existing Grafana dashboard provisioning config
   (`infrastructure/observability/grafana/provisioning/dashboards/`) contains
   at least one panel with a Prometheus query referencing
   `clive_llm_cost_usd_total`. Verifiable by inspection of the dashboard JSON.

6. **/status includes spend** — the `/status` Telegram command response
   includes today's LLM spend in USD (minimum 4 decimal places) and either
   the configured daily cap value or the string "no cap set" if
   `DAILY_SPEND_CAP_USD` is unset. Verifiable by unit test of the /status
   handler.

7. **CI passes** — the SQL migration for `llm_usage` passes the idempotency
   test (run twice, no error); unit tests for spend cap logic, rate limit
   logic, and /status spend display all pass; all pre-existing tests continue
   to pass. The CI pipeline (`ci.yml`) exits green.

## Rationale

Seven criteria span the full Block 20 delivery surface: schema persistence,
cap enforcement, rate enforcement, metrics exposure, dashboard visibility,
surface integration, and CI gate. Each criterion is verifiable from repo
artefacts (SQL files, source code, dashboard JSON, test results); no criterion
requires subjective judgment or a live system.

## Consequences

- v0.6 sign-off is blocked until all seven criteria are simultaneously true.
- No partial sign-off is permitted.
- Criterion 2 must be covered by a unit test that mocks the database read and
  LLM client — no live LLM call required in CI.
- Model pricing for unknown models defaults to 0.0; this does not block any
  criterion but should be logged as a warning in Block 8.

## Related Decisions

- D-125 — CLIVE v0.6 scope approved
- D-006 — Confirmation gate (spend cap behaviour)
- D-003 — Event bus principle (cap_exceeded event routing)
- D-106 — v0.3 acceptance criteria (structural template)
