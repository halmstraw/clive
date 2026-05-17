"""Block 2 — Dashboard push receiver (v0.11, D-146).

Block 13 pushes events to the dashboard via Block 4 egress.
This module handles those inbound push requests.

Endpoints registered in main.py:
  POST /push/response          — query.response from Block 13
  POST /push/action-confirmation — action.confirmation_requested from Block 13
  POST /push/action-outcome    — action.rejected from Block 13
  POST /push/alert             — alerts from Block 13
  POST /push/deletion-result   — deletion.complete / deletion.not_found

D-025: push endpoints must be idempotent. Storing the same response twice
for the same event_id is harmless (overwrites with same data).

D-146: the dashboard receives broadcasts. The dashboard frontend is responsible
for filtering/displaying relevant events based on the current conversation.
"""

from __future__ import annotations

import structlog
from aiohttp import web

from .api import set_pending_response

log = structlog.get_logger()

# In-memory store for pending confirmation requests.
# Keyed by action_request_id. Frontend polls /api/pending to see these.
# (Pending actions are also retrieved from Block 13 via /retrieve/pending-actions
# which is the authoritative source. This in-memory store is for real-time display.)
_pending_confirmations: dict[str, dict] = {}
_recent_alerts: list[dict] = []  # last N alerts for dashboard display


async def handle_response_push(request: web.Request) -> web.Response:
    """POST /push/response — receive query.response from Block 13.

    Stores the response keyed by conversation_id for /api/response polling.
    D-025: idempotent (overwrite on duplicate event_id is harmless).
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    conversation_id = data.get("conversation_id", "")
    event_id = data.get("event_id", "")

    if not conversation_id:
        log.warning("dashboard_response_push_no_conversation_id", event_id=event_id)
        return web.json_response({"status": "accepted"})

    set_pending_response(conversation_id, data)
    log.info("dashboard_response_received", event_id=event_id, conversation_id=conversation_id)
    return web.json_response({"status": "accepted"})


async def handle_confirmation_push(request: web.Request) -> web.Response:
    """POST /push/action-confirmation — receive action.confirmation_requested from Block 13.

    Stores the pending action for display. The authoritative pending list
    is retrieved via /api/pending → Block 13 /retrieve/pending-actions.
    This endpoint provides real-time notification to the dashboard.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    action_request_id = data.get("action_request_id", "")
    event_id = data.get("event_id", "")

    if action_request_id:
        _pending_confirmations[action_request_id] = data

    log.info(
        "dashboard_confirmation_received",
        event_id=event_id,
        action_request_id=action_request_id,
    )
    return web.json_response({"status": "accepted"})


async def handle_alert_push(request: web.Request) -> web.Response:
    """POST /push/alert — receive alerts from Block 13."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    # Keep last 20 alerts in memory for dashboard display
    _recent_alerts.insert(0, data)
    del _recent_alerts[20:]

    log.info(
        "dashboard_alert_received",
        event_id=data.get("event_id"),
        severity=data.get("severity"),
        title=data.get("title"),
    )
    return web.json_response({"status": "accepted"})


async def handle_action_outcome_push(request: web.Request) -> web.Response:
    """POST /push/action-outcome — receive action.rejected from Block 13."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    action_request_id = data.get("action_request_id", "")
    _pending_confirmations.pop(action_request_id, None)  # Remove from display

    log.info(
        "dashboard_action_outcome_received",
        event_id=data.get("event_id"),
        event_type=data.get("event_type"),
    )
    return web.json_response({"status": "accepted"})


async def handle_deletion_result_push(request: web.Request) -> web.Response:
    """POST /push/deletion-result — receive deletion.complete or deletion.not_found."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    log.info(
        "dashboard_deletion_result_received",
        event_id=data.get("event_id"),
        event_type=data.get("event_type"),
    )
    return web.json_response({"status": "accepted"})
