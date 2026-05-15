---
id: D-125
title: CLIVE v0.6 scope approved — Block 20 (Cost/Rate Management)
status: Accepted
date: 2026-05-15
blocks: Block 20 (Cost/Rate), Block 8 (Query), Block 13 (Orchestrator), Block 16 (Storage), Block 23 (Telegram), Block 25 (Observability), Block 27 (IaC), Block 28 (CI/CD)
agents: Intelligence Agent, Systems Agent, Knowledge Agent, Experience Agent, Infrastructure Agent
---

## Context

CLIVE v0.5 was signed off on 15 May 2026 (D-124). Block 25 (Observability) is
now complete — Prometheus, Loki, Grafana, and application-level instrumentation
are all live. LLM calls are being made on every query but token usage, spend,
and rate pressure are not tracked or controlled. Three options were considered
for v0.6.

## Options Considered

A. **Block 20 (Cost/Rate Management)** — LLM token tracking, daily spend cap,
   inbound rate limiting, cost metrics in Grafana, /status updated with spend
   data. Self-contained, natural complement to the observability stack just
   shipped. Low coupling risk.

B. **Block 11 full (Cross-Session Memory)** — entity tracking, conversation
   summaries, CLIVE remembers named facts across sessions. High day-to-day
   value for the owner; moderate complexity requiring careful Block 16 schema
   design.

C. **Block 9 deeper + Block 4 egress (More Actions + Proactive Messaging)** —
   CLIVE initiates messages to the owner, Action Layer expanded with new action
   types. Higher coupling across blocks; largest step toward ambient presence
   but highest implementation risk.

## Decision

Option A. v0.6 delivers Block 20 (Cost/Rate Management):

- **LLM usage tracking** — every LLM call from Block 8 records model name,
  prompt_tokens, completion_tokens, estimated_cost_usd, and timestamp to a new
  `clive_app.llm_usage` PostgreSQL table. Model pricing is a configurable
  Python dict in the query service, with per-model overrides supported via
  environment variables.

- **Daily spend cap** — a `DAILY_SPEND_CAP_USD` environment variable
  (optional; no cap if unset). Before each LLM call, Block 8 sums today's
  spend from `llm_usage`. If spend is at or above cap: Block 8 returns a
  canned "daily limit reached" response; no LLM call is made; Block 8 emits a
  `cost.cap_exceeded` event to Block 13; Block 13 routes an owner notification
  to Block 23 (Telegram). D-006 compliant: spend is the irreversible action;
  the cap is the confirmation gate. D-003 compliant: notification routes via
  Block 13.

- **Inbound rate limiting** — a `RATE_LIMIT_QUERIES_PER_HOUR` environment
  variable (optional; no limit if unset). Block 23 (Telegram handler) tracks
  query count in the current clock hour. Queries exceeding the limit receive a
  polite rejection and are not forwarded to the orchestrator. Counter resets at
  the top of each hour.

- **Prometheus metrics** — Block 8 exposes `clive_llm_tokens_total{model,
  type}` (type = prompt | completion) and `clive_llm_cost_usd_total{model}`
  counters. Block 23 exposes `clive_rate_limited_total`. Both at the existing
  `/metrics` endpoints; no new ports required.

- **Grafana cost panel** — at least one new panel added to the existing Grafana
  dashboard showing daily LLM spend sourced from `clive_llm_cost_usd_total`.

- **/status includes spend** — the `/status` Telegram command response
  includes today's LLM spend (USD, 4 decimal places) and the configured daily
  cap (or "no cap set" if `DAILY_SPEND_CAP_USD` is unset).

## Rationale

Block 20 is the tightest scope with clear acceptance criteria and no dependency
on unbuilt blocks. LLM costs are real and growing; a spend cap prevents
accidental bill shock. The observability stack (Block 25) is live and the
Prometheus plumbing already exists — adding cost counters and a Grafana panel
is incremental. Block 11 full memory (Option B) is high-value and is the
natural candidate for v0.7.

## Consequences

- Block 20 is the primary v0.6 delivery. All other blocks are touched only as
  instrumentation targets.
- `clive_app.llm_usage` schema migration must be idempotent (D-008, standard
  SQL init constraints).
- Model pricing dict ships with known prices for `claude-3-5-sonnet`,
  `claude-3-haiku`, `text-embedding-3-small`. Unknown models default to
  cost = 0.0 with a warning logged.
- Block 21 (Evolution Engine) remains paused.
- Business Layer (Blocks 30–38) remains out of scope per D-036.
- Block 11 full memory deferred to v0.7.

## Related Decisions

- D-124 — CLIVE v0.5 signed off
- D-003 — Event bus principle
- D-006 — Confirmation gate (spend cap as gate for irreversible LLM spend)
- D-065 — PostgreSQL/pgvector (llm_usage table in same instance)
- D-077 — LiteLLM abstraction (token data sourced from LiteLLM response)
- D-117 — Block 25 technology stack
