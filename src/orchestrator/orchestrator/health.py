"""HTTP health endpoint and API routes for Block 13.

v0.3: added /retrieve/document-by-filename for T8 deletion lookup (D-109).
v0.4: added /retrieve/document-list (/list command) and /retrieve/status
      (/status command); both route through orchestrator per D-003/D-043.
v0.5: added /alerts — Grafana webhook receiver; emits alert.triggered events
      on the internal bus per D-003/D-118.
      added /metrics — Prometheus scrape endpoint (D-122 Phase 2).
v0.11: added /retrieve/conversation-history and /retrieve/pending-actions
       for Block 2 web dashboard (D-146, D-147 AC-5/AC-6).
v0.12: added /retrieve/action-history and /retrieve/workers (D-149).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .bus import bus
from .events.schema import CLIVEEvent
from .events.taxonomy import ALERT_TRIGGERED
from .retrieval import (
    get_conversation_history,
    get_pending_actions,
    retrieve,
    retrieve_action_history,
    retrieve_document_by_filename,
    retrieve_document_list,
    retrieve_status,
    retrieve_system_document,
    retrieve_workers,
)

log = structlog.get_logger()


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    await asyncio.sleep(0)
    return web.json_response({"status": "ok", "block": 13})


async def handle_metrics(request: web.Request) -> web.Response:  # noqa: ARG001
    """Expose Prometheus metrics for scraping (D-122 Phase 2)."""
    await asyncio.sleep(0)
    data = generate_latest()
    return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})


async def handle_event_intake(request: web.Request) -> web.Response:
    """Accept inbound events from Block 8 and Block 23, route through bus."""
    data = await request.json()
    event = CLIVEEvent(**data)
    await bus.publish(event)
    return web.json_response({"status": "accepted"})


async def handle_alerts(request: web.Request) -> web.Response:
    """Receive Grafana webhook payloads and emit alert.triggered events (D-118).

    POST /alerts — internal endpoint on clive-internal network only.
    No authentication required (network-level isolation).

    Grafana sends a batch payload with an 'alerts' list.  One alert.triggered
    event is emitted per alert entry.  Returns 200 on success or empty batch.
    Returns 400 for malformed JSON or missing 'alerts' field.
    Never returns 5xx — Grafana would retry indefinitely.
    """
    try:
        body = await request.json()
    except Exception:
        log.warning("alerts_malformed_json")
        return web.json_response({"error": "invalid JSON"}, status=400)

    if not isinstance(body, dict) or "alerts" not in body:
        log.warning("alerts_missing_field", body_keys=list(body.keys()) if isinstance(body, dict) else None)
        return web.json_response({"error": "missing 'alerts' field"}, status=400)

    alerts = body["alerts"]
    if not isinstance(alerts, list):
        log.warning("alerts_field_not_list")
        return web.json_response({"error": "'alerts' must be a list"}, status=400)

    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        alert_name = labels.get("alertname", "unknown")
        severity = labels.get("severity", "unknown")
        status = alert.get("status", "unknown")
        summary = annotations.get("summary") or body.get("title", "")
        description = annotations.get("description") or body.get("message", "")
        started_at = alert.get("startsAt", "")
        fingerprint = alert.get("fingerprint", "")

        log.info(
            "alert_received",
            alert_name=alert_name,
            severity=severity,
            status=status,
        )

        event = CLIVEEvent(
            event_type=ALERT_TRIGGERED,
            source_block=25,
            payload={
                "alert_name": alert_name,
                "severity": severity,
                "status": status,
                "summary": summary,
                "description": description,
                "started_at": started_at,
                "fingerprint": fingerprint,
            },
        )
        await bus.publish(event)

    return web.json_response({"status": "accepted"})


async def handle_retrieve_knowledge(request: web.Request) -> web.Response:
    """Broker retrieval call to Block 16 (D-043)."""
    data = await request.json()
    result = await retrieve(
        retrieval_query=data["retrieval_query"],
        zone_scope=data["zone_scope"],
        result_limit=data.get("result_limit", 20),
        conversation_id=data.get("conversation_id"),
    )
    return web.json_response(result)


async def handle_retrieve_system_document(request: web.Request) -> web.Response:
    """Broker system document retrieval (D-048)."""
    data = await request.json()
    result = await retrieve_system_document(
        document_type=data["document_type"],
        zone_scope=data["zone_scope"],
        version_id=data.get("version_id"),
    )
    return web.json_response(result)


async def handle_retrieve_document_by_filename(request: web.Request) -> web.Response:
    """Look up source_keys for a given filename in Block 16 (D-109, T8 deletion).

    Returns {source_keys: [...], chunk_count: N} or 404 if not found.
    Used by Block 23's /delete command to verify the document exists before
    emitting action.pending to Block 9.
    """
    data = await request.json()
    filename = data.get("filename", "")
    zone_scope = data.get("zone_scope", "personal")

    if not filename:
        return web.json_response({"error": "filename required"}, status=400)

    result = await retrieve_document_by_filename(filename=filename, zone_scope=zone_scope)
    if not result["source_keys"]:
        return web.json_response({"error": "not found"}, status=404)

    return web.json_response(result)


async def handle_retrieve_document_list(request: web.Request) -> web.Response:
    """Return list of ingested documents for Block 23 /list command (v0.4).

    Returns {documents: [{filename, source_key, chunk_count, ingested_at}], total: N}.
    """
    data = await request.json()
    zone_scope = data.get("zone_scope", "personal")
    limit = int(data.get("limit", 25))
    result = await retrieve_document_list(zone_scope=zone_scope, limit=limit)
    return web.json_response(result)


async def handle_retrieve_status(request: web.Request) -> web.Response:
    """Return system status metrics for Block 23 /status command (v0.4).

    Returns doc_count, chunk_count, last_doc_name, last_doc_at, last_query_at.
    """
    data = await request.json()
    zone_scope = data.get("zone_scope", "personal")
    result = await retrieve_status(zone_scope=zone_scope)
    return web.json_response(result)


# ---------------------------------------------------------------------------
# v0.11 — Block 2/5 dashboard retrieval endpoints (D-146, D-147 AC-5/AC-6)
# ---------------------------------------------------------------------------

async def handle_retrieve_conversation_history(request: web.Request) -> web.Response:
    """Return conversation turns for a given conversation_id.

    D-147 AC-6: used by dashboard /api/history to show shared conversation
    history. Same conversation_turns table read by Block 8.

    POST /retrieve/conversation-history
    Body: {"conversation_id": "uuid-string", "limit": N (optional)}
    Returns: {"turns": [{"role": ..., "content": ...}], "conversation_id": ...}
    """
    data = await request.json()
    raw_id = data.get("conversation_id")
    if not raw_id:
        return web.json_response({"error": "conversation_id required"}, status=400)

    try:
        conversation_id = uuid.UUID(str(raw_id))
    except ValueError:
        return web.json_response({"error": "invalid conversation_id"}, status=400)

    limit = int(data.get("limit", 50))
    turns = await get_conversation_history(conversation_id, limit=limit)
    return web.json_response({"turns": turns, "conversation_id": str(conversation_id)})


async def handle_retrieve_pending_actions(request: web.Request) -> web.Response:
    """Return pending (unresolved) Block 9 actions for the dashboard.

    D-147 AC-5: used by dashboard /api/pending to list actions awaiting
    owner confirmation. Only status='pending' and not-yet-expired rows.

    POST /retrieve/pending-actions
    Body: {"zone_scope": "personal"}
    Returns: {"actions": [...], "count": N}
    """
    data = await request.json()
    zone_scope = data.get("zone_scope", "personal")
    actions = await get_pending_actions(zone_scope=zone_scope)
    return web.json_response({"actions": actions, "count": len(actions)})


# ---------------------------------------------------------------------------
# v0.12 — Self-knowledge retrieval endpoints (D-149)
# ---------------------------------------------------------------------------

async def handle_retrieve_action_history(request: web.Request) -> web.Response:
    """Return resolved actions from the last N days.

    POST /retrieve/action-history
    Body: {"zone_scope": "personal", "days": 7}
    Returns: {"actions": [...], "total": N, "days": N}
    """
    data = await request.json()
    zone_scope = data.get("zone_scope", "personal")
    days = int(data.get("days", 7))
    result = await retrieve_action_history(zone_scope=zone_scope, days=days)
    return web.json_response(result)


async def handle_retrieve_workers(request: web.Request) -> web.Response:
    """Return registered workers with schedule and health information.

    POST /retrieve/workers
    Body: {} (no body required)
    Returns: {"workers": [...], "total": N}
    """
    result = await retrieve_workers()
    return web.json_response(result)


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_post("/events", handle_event_intake)
    app.router.add_post("/alerts", handle_alerts)
    app.router.add_post("/retrieve/knowledge", handle_retrieve_knowledge)
    app.router.add_post("/retrieve/system-document", handle_retrieve_system_document)
    app.router.add_post("/retrieve/document-by-filename", handle_retrieve_document_by_filename)
    app.router.add_post("/retrieve/document-list", handle_retrieve_document_list)
    app.router.add_post("/retrieve/status", handle_retrieve_status)
    # v0.11 — Block 2/5 dashboard endpoints (D-146)
    app.router.add_post("/retrieve/conversation-history", handle_retrieve_conversation_history)
    app.router.add_post("/retrieve/pending-actions", handle_retrieve_pending_actions)
    # v0.12 — self-knowledge endpoints (D-149)
    app.router.add_post("/retrieve/action-history", handle_retrieve_action_history)
    app.router.add_post("/retrieve/workers", handle_retrieve_workers)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
