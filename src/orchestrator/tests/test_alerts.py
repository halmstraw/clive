"""Tests for POST /alerts — Grafana webhook receiver (D-118, v0.5).

Tests exercise handle_alerts directly, mocking request.json() and the
bus singleton.  No HTTP server is required — consistent with the rest of
this test suite (see test_action.py, test_retrieval.py).

Covers:
- Valid payload with one alert: emits one alert.triggered event, returns 200.
- Malformed JSON: returns 400, no events emitted.
- Empty alerts array: returns 200, no events emitted.
- Missing 'alerts' field: returns 400, no events emitted.
- Multiple alerts: one event emitted per alert.
- Missing severity label: defaults to 'unknown'.
- Missing annotations.summary: falls back to top-level 'title'.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from orchestrator.events.schema import CLIVEEvent
from orchestrator.events.taxonomy import ALERT_TRIGGERED
from orchestrator.health import handle_alerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(body: dict | None, malformed: bool = False) -> MagicMock:
    """Build a mock aiohttp Request whose .json() returns the given body.

    Pass malformed=True to simulate a JSON decode error.
    """
    req = MagicMock()
    if malformed:
        req.json = AsyncMock(side_effect=json.JSONDecodeError("bad json", "", 0))
    else:
        req.json = AsyncMock(return_value=body)
    return req


def _grafana_payload(alerts: list[dict] | None = None, **overrides) -> dict:
    """Build a minimal Grafana-shaped webhook payload."""
    base: dict = {
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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_payload_emits_alert_triggered_event():
    """Valid Grafana payload with one alert emits one alert.triggered event."""
    emitted: list[CLIVEEvent] = []

    req = _make_request(_grafana_payload())

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 200
    body = json.loads(resp.body)
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
async def test_malformed_json_returns_400():
    """Malformed JSON body must return 400; no events emitted."""
    emitted: list[CLIVEEvent] = []

    req = _make_request(None, malformed=True)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 400
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_empty_alerts_array_returns_200_no_events():
    """Empty alerts list must return 200 but emit no events."""
    emitted: list[CLIVEEvent] = []

    req = _make_request(_grafana_payload(alerts=[]))

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["status"] == "accepted"
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_missing_alerts_field_returns_400():
    """Payload without 'alerts' key must return 400."""
    emitted: list[CLIVEEvent] = []

    req = _make_request({"status": "firing", "receiver": "clive-orchestrator"})

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 400
    assert len(emitted) == 0


@pytest.mark.asyncio
async def test_multiple_alerts_emit_one_event_each():
    """Three alerts in one payload must produce three alert.triggered events."""
    emitted: list[CLIVEEvent] = []

    alerts = [
        _grafana_alert(alertname="ServiceDown", fingerprint="fp1"),
        _grafana_alert(alertname="HighMemory", severity="warning", fingerprint="fp2"),
        _grafana_alert(alertname="DiskFull", severity="critical", fingerprint="fp3"),
    ]
    req = _make_request(_grafana_payload(alerts=alerts))

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 200
    assert len(emitted) == 3
    fingerprints = {e.payload["fingerprint"] for e in emitted}
    assert fingerprints == {"fp1", "fp2", "fp3"}


@pytest.mark.asyncio
async def test_missing_severity_defaults_to_unknown():
    """Alert with no severity label must use 'unknown' as the default."""
    emitted: list[CLIVEEvent] = []

    alert_no_severity = {
        "status": "firing",
        "labels": {"alertname": "NoSeverityAlert"},  # no 'severity' key
        "annotations": {},
        "startsAt": "2026-05-15T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "",
        "fingerprint": "xyz999",
    }
    req = _make_request(_grafana_payload(alerts=[alert_no_severity]))

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 200
    assert len(emitted) == 1
    assert emitted[0].payload["severity"] == "unknown"
    assert emitted[0].payload["alert_name"] == "NoSeverityAlert"


@pytest.mark.asyncio
async def test_summary_falls_back_to_title_when_annotation_absent():
    """When annotations.summary is absent, the top-level 'title' is used."""
    emitted: list[CLIVEEvent] = []

    alert_no_summary = {
        "status": "firing",
        "labels": {"alertname": "TestAlert", "severity": "warning"},
        "annotations": {},  # no summary annotation
        "startsAt": "2026-05-15T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "",
        "fingerprint": "fallback1",
    }
    payload = _grafana_payload(alerts=[alert_no_summary])
    payload["title"] = "[FIRING:1] TestAlert"
    req = _make_request(payload)

    with patch("orchestrator.health.bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))
        resp = await handle_alerts(req)

    assert resp.status == 200
    assert len(emitted) == 1
    assert emitted[0].payload["summary"] == "[FIRING:1] TestAlert"
