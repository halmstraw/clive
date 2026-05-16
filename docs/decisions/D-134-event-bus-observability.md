# D-134 — Event Bus Observability: structured logging + Grafana dashboard

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks affected:** Block 13 (Orchestrator/Event Bus), Block 25 (Observability), Block 28 (CI/CD)  
**Recorded by:** Architect

---

## Context

CLIVE v0.7 is live. Block 13's in-process event bus routes all inter-block
communication (D-003), but event flow was invisible in Grafana. The
`bus.py._dispatch` method had no log statement — successfully routed events
produced no observable output. Additionally, `structlog` had no explicit
configuration in any service, defaulting to `ConsoleRenderer` (human-readable
text), which Loki's `| json` parser cannot extract fields from.

The goal: a dedicated Grafana dashboard showing a live feed of event bus
activity — event type, source block, conversation ID, and payload summary.

---

## Decision

Three coordinated changes implement event bus observability:

### 1. Structured JSON logging for the orchestrator

`structlog.configure()` added to `orchestrator/main.py` before any loggers are
created. Processors: `merge_contextvars`, `add_log_level`, `TimeStamper(iso)`,
`StackInfoRenderer`, `JSONRenderer`. This makes all orchestrator log lines
machine-parseable JSON, enabling Loki's `| json` extractor.

This does not change what is logged — it changes the format from
`ConsoleRenderer` key=value text to JSON. The existing "Application Logs"
panel in `system_overview.json` continues to work (it displays the raw log line
regardless of format).

### 2. `event_dispatched` log emitted on every routed event

`bus.py._dispatch` now emits `log.info("event_dispatched", ...)` at the start
of each dispatch with five fields:
- `event_type` — e.g. `query.received`
- `source_block` — integer, e.g. `23`
- `conversation_id` — UUID string or `null`
- `event_id` — UUID string
- `payload_keys` — list of payload field names (summary without exposing values)

This is the primary signal for the Grafana event bus dashboard.

### 3. New Grafana dashboard: `event_bus.json`

A dedicated "CLIVE Event Bus" dashboard (`uid: clive-event-bus`) with two panels:

**Panel 1 — "Event Bus — Dispatched Events"** (full width, 20 rows, Logs type):
```logql
{container="clive-orchestrator"} | json | event="event_dispatched"
  | line_format "{{.event_type}} | src={{.source_block}} | conv={{.conversation_id}} | payload={{.payload_keys}}"
```
Refresh: 10s. Shows all successfully routed events as a live feed.

**Panel 2 — "Bus Errors — Alignment Rejections & Delivery Failures"** (full width, 10 rows, Logs type):
```logql
{container="clive-orchestrator"} | json | level=~"warning|error"
```
Captures `alignment_rejected`, `delivery_failed_dead_letter`,
`queue_full_backpressure`, and `event_held_override_active`.

The dashboard is deployed alongside `system_overview.json` via both Ansible
(`compose-deploy/tasks/main.yml`) and the GHA deploy workflow (`deploy.yml`).
The Grafana provisioner auto-discovers all `.json` files in the dashboards
directory.

---

## Alternatives considered

**Add panel to `system_overview.json`** — rejected. The dashboard already spans
36+ grid rows with 10 panels. A dedicated dashboard is cleaner and allows a
10s refresh without affecting the 30s system overview refresh.

**Use `| logfmt` parser instead of `| json`** — rejected. structlog's default
`ConsoleRenderer` output is not logfmt-compatible (it has a timestamp/level
header that logfmt cannot parse). JSON is the correct production format and
aligns with standard container logging practice.

---

## Impact

- `bus.py` and `main.py`: orchestrator changes. All 45 unit tests pass.
- `event_bus.json`: new file, provisioned automatically.
- `main.yml` and `deploy.yml`: one copy task / one `cp` line added each.
- No schema changes. No secret changes.
