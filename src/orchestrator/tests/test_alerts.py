"""Tests for POST /alerts — Grafana webhook receiver (D-118, v0.5).

Covers:
- Valid payload with one alert: emits one alert.triggered event, returns 200.
- Malformed JSON: returns 400, no events emitted.
- Empty alerts array: returns 200, no events emitted.
- Missing 'alerts' field: returns 400, no events emitted.
- Multiple alerts: one event emitted per alert.
- Payload fields mapped correctly (alert_name, severity, status, summary,
  description, started_at, fingerprint).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from orchestrator.events.schema import AlignmentResult, CLIVEEvent
from orchestrator.events.taxonomy import ALERT_TRIGGERED
from orchestrator.health import start_health_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grafana_payload(alerts: list[dict] | None = None, **overrides) -> dict:
    """Build a minimal Grafana-shaped webhook payload."""
    base = {
        "receiver": "clive-orchestrator",
        "status": "firing",
        "alerts": alerts if alerts is not None else [_grafana_alert()],
        "groupLabels": {},
        "commonLabels": {},
        "commonAnnotations": {},
        "externalURL": "http://grafana:3000",
        "version": "1",
        "groupKey": "group-key-1",
        "truncatedAlerts": 0,
        "title": "[FIRING:1] ServiceDown",
        "message": "orchestrator is down",
    }
    base.update(overrides)
    return base


def _grafana_alert(
    alertname: str = "ServiceDown",
    severity: str = "critical",
    status: str = "firing",
    summary: str = "orchestrator is down",
    description: str = "The orchestrator container is not responding.",
    started_at: str = "2026-05-15T10:00:00Z",
    fingerprint: str = "abc123",
) -> dict:
    return {
        "status": status,
        "labels": {"alertname": alertname, "severity": severity},
        "annotations": {"summary": summary, "description": description},
        "startsAt": started_at,
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus:9090/graph",
        "fingerprint": fingerprint,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(aiohttp_client):
    """Spin up a real aiohttp test server with the health app.

    We patch bus.publish and the alignment/audit dependencies so no DB or
    bus infrastructure is needed.
    """
    app = web.Application()
    from orchestrator.health import (
        handle_alerts,
        handle_event_intake,
        handle_health,
    )
    app.router.add_get("/health", handle_health)
    app.router.add_post("/events", handle_event_intake)
    app.router.add_post("/alerts", handle_alerts)
    return await aiohttp_client(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_payload_emits_alert_triggered_event(aiohttp_client):
    """Valid Grafana payload with one alert emits one alert.triggered event."""
    emitted: list[CLIVEEvent] = []

    async def fake_publish(event: CLIVEEvent) -> None:
        emitted.append(event)

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=fake_publish)
        resp = await client.post(
            "/alerts",
            data=json.dumps(_grafana_payload()),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "accepted"

    assert len(emitted) == 1
    evt = emitted[0]
    assert evt.event_type == ALERT_TRIGGERED
    assert evt.source_block == 25
    assert evt.payload["alert_name"] == "ServiceDown"
    assert evt.payload["severity"] == "critical"
    assert evt.payload["status"] == "firing"
    assert evt.payload["summary"] == "orchestrator is down"
    assert evt.payload["description"] == "The orchestrator container is not responding."
    assert evt.payload["started_at"] == "2026-05-15T10:00:00Z"
    assert evt.payload["fingerprint"] == "abc123"


@pytest.mark.asyncio
async def test_malformed_json_returns_400(aiohttp_client):
    """Malformed JSON body must return 400; no events emitted."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data="this is not json {{{",
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 400
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_empty_alerts_array_returns_200_no_events(aiohttp_client):
    """Empty alerts list must return 200 but emit no events."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data=json.dumps(_grafana_payload(alerts=[])),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "accepted"
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_missing_alerts_field_returns_400(aiohttp_client):
    """Payload without 'alerts' key must return 400."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data=json.dumps({"status": "firing", "receiver": "clive-orchestrator"}),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 400
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_multiple_alerts_emit_one_event_each(aiohttp_client):
    """Three alerts in one payload must produce three alert.triggered events."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    alerts = [
        _grafana_alert(alertname="ServiceDown", fingerprint="fp1"),
        _grafana_alert(alertname="HighMemory", severity="warning", fingerprint="fp2"),
        _grafana_alert(alertname="DiskFull", severity="critical", fingerprint="fp3"),
    ]

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data=json.dumps(_grafana_payload(alerts=alerts)),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 200
    assert len(emitted) == 3
    fingerprints = [e.payload["fingerprint"] for e in emitted]
    assert set(fingerprints) == {"fp1", "fp2", "fp3"}


@pytest.mark.asyncio
async def test_missing_severity_defaults_to_unknown(aiohttp_client):
    """Alert with no severity label must use 'unknown' as default."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    alert_no_severity = {
        "status": "firing",
        "labels": {"alertname": "NoSeverityAlert"},
        "annotations": {},
        "startsAt": "2026-05-15T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "",
        "fingerprint": "xyz999",
    }

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data=json.dumps(_grafana_payload(alerts=[alert_no_severity])),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 200
    assert len(emitted) == 1
    assert emitted[0].payload["severity"] == "unknown"
    assert emitted[0].payload["alert_name"] == "NoSeverityAlert"


@pytest.mark.asyncio
async def test_summary_falls_back_to_title_when_annotation_absent(aiohttp_client):
    """When annotations.summary is absent, payload.title is used as summary."""
    emitted: list[CLIVEEvent] = []

    app = web.Application()
    from orchestrator.health import handle_alerts
    app.router.add_post("/alerts", handle_alerts)
    client = await aiohttp_client(app)

    alert_no_summary = {
        "status": "firing",
        "labels": {"alertname": "TestAlert", "severity": "warning"},
        "annotations": {},  # no summary
        "startsAt": "2026-05-15T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "",
        "fingerprint": "fallback1",
    }
    payload = _grafana_payload(alerts=[alert_no_summary])
    payload["title"] = "[FIRING:1] TestAlert"

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await client.post(
            "/alerts",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status == 200
    assert emitted[0].payload["summary"] == "[FIRING:1] TestAlert"
