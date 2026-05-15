---
id: D-122
title: CLIVE v0.5 scope approved — Block 25 observability complete delivery
status: Accepted
date: 2026-05-15
blocks: Block 25 (Observability), Block 13 (Orchestrator), Block 8 (Query), Block 14/15 (Processing), Block 23 (Telegram), Block 27 (IaC), Block 28 (CI/CD)
agents: Infrastructure Agent, Systems Agent, Intelligence Agent, Knowledge Agent, Experience Agent
---

## Context

CLIVE v0.4 was signed off on 15 May 2026 (D-120). The infrastructure layer of
Block 25 observability was implemented during v0.4: all seven Compose services
(Prometheus, Loki, Grafana, Promtail, node-exporter, postgres-exporter, cAdvisor)
are deployed via Docker Compose, Ansible deploys all config files, the orchestrator
`/alerts` webhook is implemented (health.py), `ALERT_TRIGGERED` is in the event
taxonomy, and the Grafana contact point is wired to `http://orchestrator:8080/alerts`
per D-118. Phase 2 — application-level metrics instrumentation — was not included in
v0.4. v0.5 completes Block 25 by adding Phase 2.

## Options Considered

A. Split release: ship Phase 1 sign-off in v0.4, Phase 2 as a standalone v0.5 —
   creates an intermediate state where observability infrastructure exists but
   application metrics are not yet scraped; complicates acceptance criteria.

B. Ship Phase 1 and Phase 2 together as v0.5, treating v0.4 as the last
   application-feature release before full observability is live — clean boundary,
   single sign-off event, no intermediate partial state.

C. Defer Phase 2 to v0.6 — delays full Block 25 completion with no material benefit;
   the instrumentation work is small.

## Decision

Option B. v0.5 delivers Block 25 in full:

- **Phase 1 — infrastructure observability** (already implemented as of v0.4):
  Prometheus, Loki, Grafana, Promtail, node-exporter, postgres-exporter, cAdvisor
  deployed as seven additional Compose services. Alert routing via orchestrator
  webhook per D-118. Grafana contact point configured to POST to
  `http://orchestrator:8080/alerts`.

- **Phase 2 — application-level metrics** (v0.5 implementation target):
  `prometheus_client` instrumentation added to orchestrator, query, processing,
  and telegram services. Each service exposes a `/metrics` HTTP endpoint scraped
  by Prometheus. Minimum viable metric set per service:

  | Service | Port | Metrics |
  |---|---|---|
  | orchestrator | 8080 | `clive_events_published_total{event_type}`, `clive_audit_writes_total` |
  | query | 8081 | `clive_queries_total`, `clive_query_duration_seconds` (histogram), `clive_retrieval_chunks_returned_total` |
  | processing | 8083 | `clive_ingest_total{status}` (status=processed\|rejected), `clive_chunks_created_total`, `clive_processing_duration_seconds` (histogram) |
  | telegram | 8082 | `clive_telegram_commands_total{command}` (command=query\|ingest\|delete\|list\|status\|feedback\|other) |

  `prometheus-client` added to each service's `pyproject.toml` dependencies.

  Prometheus scrape config (`prometheus.yml`) updated with job names:
  `clive-orchestrator`, `clive-query`, `clive-processing`, `clive-telegram`.

- Phase 1 and Phase 2 ship together as v0.5; no split release.

## Rationale

Completing Block 25 in a single release maintains a clean version boundary.
The Phase 2 instrumentation is small (counter/histogram decorators + a single
`/metrics` route per service) and has no dependencies on other v0.5 work.
D-003 compliance is maintained: metrics are read-only observations, not
inter-block communication.

## Consequences

- Block 25 is complete after v0.5 sign-off.
- Prometheus scrapes four application service `/metrics` endpoints in addition
  to the infrastructure exporters already in the scrape config.
- Alert rules in `services.yml` that reference application service job names
  must use the `clive-` prefixed names.
- Block 21 (Evolution Engine) remains paused — not in v0.5 scope.
- Business Layer (Blocks 30–38) remains out of scope per D-036.

## Related Decisions

- D-117 — Block 25 technology stack (Prometheus, Loki, Grafana)
- D-118 — Alert routing via orchestrator webhook
- D-120 — CLIVE v0.4 signed off
- D-003 — Event bus principle (metrics endpoints are passive; no bus bypass)
