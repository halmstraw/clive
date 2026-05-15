---
id: D-123
title: CLIVE v0.5 acceptance criteria defined
status: Accepted
date: 2026-05-15
blocks: Block 25 (Observability), Block 13 (Orchestrator), Block 8 (Query), Block 14/15 (Processing), Block 23 (Telegram), Block 28 (CI/CD)
agents: Infrastructure Agent, Systems Agent, Intelligence Agent, Knowledge Agent, Experience Agent
---

## Context

v0.5 scope is approved (D-122). Before implementation proceeds, acceptance
criteria must be defined so that "done" is unambiguous and sign-off can be
verified objectively. These criteria gate the v0.5 sign-off decision.

## Options Considered

A. Minimal criteria (infra only) — only verify that the seven Compose services
   start and Grafana is reachable; defer application metrics verification.
   Rejected: leaves Phase 2 unverified; defeats the purpose of shipping both
   together.

B. Full criteria — all seven conditions covering infrastructure health, application
   metric scraping, alert rules, alert routing, end-to-end webhook flow, log
   collection, and CI.
   Accepted: complete and verifiable.

## Decision

All seven criteria must be simultaneously true for v0.5 sign-off:

1. **Compose health** — all seven observability Compose services (prometheus,
   loki, grafana, promtail, node-exporter, postgres-exporter, cadvisor) start
   and reach healthy state.

2. **Application scrape targets** — Prometheus is configured to scrape `/metrics`
   from orchestrator (port 8080), query (8081), processing (8083), and telegram
   (8082). Verified by inspection of `infrastructure/observability/prometheus/
   prometheus.yml` containing job entries `clive-orchestrator`, `clive-query`,
   `clive-processing`, `clive-telegram` with the correct targets.

3. **Alert rules exist** — at least one alert rule is defined in
   `infrastructure/observability/prometheus/rules/`. Both `services.yml` and
   `system.yml` must be present and non-empty.

4. **Grafana contact point** — `infrastructure/observability/grafana/provisioning/
   alerting/contact_points.yml` configures a webhook contact point that POSTs to
   `http://orchestrator:8080/alerts`.

5. **End-to-end alert flow** — a POST to the orchestrator `/alerts` endpoint
   with a valid Grafana webhook payload (containing an `alerts` list with at
   least one entry) produces an `alert.triggered` event in the Block 13 audit
   log (verifiable via the audit event_log table or test assertion).

6. **Log collection** — Loki is configured to collect Docker container logs via
   Promtail. Verified by inspection of
   `infrastructure/observability/promtail/config.yml` containing a Docker
   scrape config targeting the Docker socket.

7. **CI passes** — all of the following pass in the GitHub Actions CI pipeline:
   unit tests, SQL idempotency tests, and DB role privilege tests.

## Rationale

Seven criteria span the full Block 25 delivery surface — infrastructure
availability, application metric instrumentation, alert pipeline, log
collection, and CI gate. Each criterion is verifiable from artefacts in the
repo (config files, test results) or from a live system check; no criterion
requires subjective judgment.

## Consequences

- v0.5 sign-off is blocked until all seven criteria are simultaneously true.
- Criterion 5 (end-to-end alert flow) is covered by the existing e2e test in
  `tests/e2e/d106_e2e.py` or a new test targeting the `/alerts` endpoint —
  must be verified before sign-off.
- No partial sign-off is permitted; all criteria are required.

## Related Decisions

- D-122 — CLIVE v0.5 scope approved
- D-117 — Block 25 technology stack
- D-118 — Alert routing via orchestrator webhook
- D-106 — v0.3 acceptance criteria (template for this document)
