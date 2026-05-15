---
id: D-124
title: CLIVE v0.5 signed off — all seven criteria met 15 May 2026
status: Accepted
date: 2026-05-15
blocks: All blocks
agents: Architect
---

## Context

v0.5 scope was approved in D-122. Seven acceptance criteria were defined in
D-123. Implementation was completed on branch `claude/review-system-progress-6m358`
and deployed to production. The owner verified all criteria and confirmed sign-off.

## Options Considered

Not applicable — sign-off decision records a verified outcome.

## Decision

CLIVE v0.5 is signed off. All seven D-123 criteria were simultaneously true at
time of sign-off on 15 May 2026:

1. ✅ All seven observability Compose services (prometheus, loki, grafana, promtail,
   node-exporter, postgres-exporter, cadvisor) started and reached healthy state.

2. ✅ Prometheus scrape config contains `clive-orchestrator` (8080), `clive-query`
   (8081), `clive-processing` (8083), and `clive-telegram` (8082) — confirmed
   in `infrastructure/observability/prometheus/prometheus.yml`.

3. ✅ Alert rules present and non-empty in
   `infrastructure/observability/prometheus/rules/services.yml` and `system.yml`.

4. ✅ Grafana contact point configured to POST to `http://orchestrator:8080/alerts`
   — confirmed in `infrastructure/observability/grafana/provisioning/alerting/
   contact_points.yml`.

5. ✅ POST to `/alerts` with a valid Grafana webhook payload produced an
   `alert.triggered` event (source_block=25) in the Block 13 audit log —
   verified on production via `docker exec`.

6. ✅ Promtail configured to collect Docker container logs via the
   `docker_containers` scrape job — confirmed in
   `infrastructure/observability/promtail/config.yml`.

7. ✅ CI passed: unit tests, SQL idempotency tests, and DB role privilege tests
   all green.

## Rationale

All seven criteria verified by owner on production. Block 25 is complete.

## Consequences

- Block 25 (Observability) is fully implemented and signed off.
- CLIVE now exposes application-level metrics (`clive_events_published_total`,
  `clive_audit_writes_total`, `clive_queries_total`, `clive_query_duration_seconds`,
  `clive_retrieval_chunks_returned_total`, `clive_ingest_total`,
  `clive_chunks_created_total`, `clive_processing_duration_seconds`,
  `clive_telegram_commands_total`) scraped by Prometheus.
- Alert pipeline is end-to-end verified: Grafana → orchestrator webhook →
  `alert.triggered` event → Block 13 audit log → Block 23 Telegram delivery.
- The Ansible `08_v04_tables.sql` deployment gap (Block 11 `conversation_turns`
  table) is fixed — will apply on next fresh VM provision.
- v0.6 planning may now begin.

## Related Decisions

- D-122 — CLIVE v0.5 scope approved
- D-123 — CLIVE v0.5 acceptance criteria
- D-120 — CLIVE v0.4 signed off
- D-117 — Block 25 observability tech stack
- D-118 — Alert routing via orchestrator webhook
