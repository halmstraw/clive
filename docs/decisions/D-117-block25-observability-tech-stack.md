---
id: D-117
title: Block 25 observability stack — Prometheus, Loki, Grafana
status: Accepted
date: 2026-05-15
blocks: Block 25, Block 27, Block 28
agents: Infrastructure Agent
---

## Context
v0.5 introduces formal observability (Block 25). Owner named Prometheus, Grafana,
and Loki as the target tools. Architect confirmed these fit the CX21 resource
envelope (~1.15 GB additional memory; ~2.65 GB total; 1.35 GB headroom).

## Decision
Block 25 is implemented using the following components, all deployed as Docker
Compose services on the existing CX21 VM alongside the application stack:

- **Prometheus** — metrics collection and alert rule evaluation
- **Loki** — log aggregation (local filesystem storage, 30-day retention)
- **Grafana** — dashboards and alert dispatch
- **Promtail** — log shipping from Docker containers to Loki via Docker socket
- **node-exporter** — VM host metrics (CPU, RAM, disk, network)
- **postgres-exporter** — PostgreSQL operational metrics
- **cAdvisor** — per-container CPU/memory/restart metrics

All seven services run on the existing `clive-internal` Docker network. Grafana
port 3000 is bound to `127.0.0.1` only. Owner access via SSH tunnel.

Config files live under `infrastructure/observability/` and are deployed to
`/home/clive/compose/observability/` on the VM by Ansible.

Application-level `/metrics` endpoints (prometheus_client instrumentation in
each Python service) are a Phase 2 deliverable, assigned to the relevant
specialist agents after Phase 1 ships.

## Consequences
Infrastructure Agent implements Phase 1. No VM upgrade required at this time —
resource headroom is sufficient. Memory pressure must be monitored after deploy;
a VM upgrade to CX31 becomes the fallback if headroom proves insufficient.
