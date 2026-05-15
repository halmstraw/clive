---
id: D-118
title: Block 25 alert routing via orchestrator webhook — D-003 compliant
status: Accepted
date: 2026-05-15
blocks: Block 25, Block 13, Block 4, Block 23
agents: Architect, Systems Agent, Infrastructure Agent
---

## Context
Grafana (Block 25) evaluates alert rules and must dispatch firing alerts to the
owner via Telegram. Two routing options existed:

A. Grafana → orchestrator webhook → Block 13 event bus → Block 4 → Telegram
B. Grafana → Telegram Bot API directly (bypasses Block 13)

Option B would create an unaudited side-channel outside the event bus, violating
the spirit of D-003 and producing gaps in the audit trail.

## Decision
Grafana dispatches alerts to `http://orchestrator:8080/alerts` (internal webhook,
existing `clive-internal` network). The orchestrator receives the payload, emits
an `alert.triggered` event on Block 13. Block 4 (Telegram surface) subscribes to
`alert.triggered` and delivers the alert to the owner via Telegram.

The `/alerts` webhook endpoint on the orchestrator is a new endpoint, implemented
by the Systems Agent as part of v0.5.

Alert payload from Grafana is a standard Grafana webhook JSON body. The
orchestrator normalises it into a structured `alert.triggered` event before
emitting on the bus.

## Consequences
All CLIVE alerts are visible in the Block 13 event audit trail. No direct
Grafana-to-Telegram path exists. Systems Agent must implement the `/alerts`
endpoint on the orchestrator before Grafana alerting is active. Infrastructure
Agent configures Grafana's contact point to use this internal URL.
