"""Block 2 — Web dashboard API endpoints (v0.11, D-146).

API routes (all require authenticated session):
  POST /api/query              — submit a query to CLIVE
  GET  /api/response           — poll for response to a query
  POST /api/history            — retrieve conversation history (shared with Telegram)
  GET  /api/pending            — list pending Block 9 confirmation requests
  POST /api/confirm/<id>       — confirm a pending action (D-006)
  POST /api/cancel/<id>        — cancel a pending action (D-006)

D-003: all reads go through Block 13's HTTP API (retrieval endpoints).
       all writes/events go through Block 13's /events endpoint.
       No direct DB calls from the dashboard service.

D-006: confirm/cancel emit action.owner_response to Block 13; they do NOT
       directly update pending_actions. Block 9 handles the lifecycle.

D-147 AC-4: query submission carries source_surface="dashboard".
D-147 AC-5: pending list + confirm/cancel via Block 13 retrieval + events.
D-147 AC-6: history reads from Block 13 /retrieve/conversation-history.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog
from aiohttp import web

from .auth import require_session

log = structlog.get_logger()

# Pending responses keyed by conversation_id (in-memory, non-persistent)
# Populated by push.py when Block 13 pushes a query.response to /push/response.
# Dashboard frontend polls /api/response?conversation_id=xxx until it appears.
_pending_responses: dict[str, dict] = {}

ORCHESTRATOR_URL = "http://orchestrator:8080"  # NOSONAR — Docker-internal


def set_pending_response(conversation_id: str, data: dict) -> None:
    """Store an inbound push response. Called by push.py."""
    _pending_responses[conversation_id] = data
    log.info("dashboard_response_stored", conversation_id=conversation_id)


async def handle_query(request: web.Request) -> web.Response:
    """POST /api/query — submit a query to CLIVE via Block 13.

    Body: {"input_text": "...", "conversation_id": "uuid (optional)"}
    Returns: {"conversation_id": "...", "event_id": "..."}

    D-147 AC-4: carries source_surface="dashboard" so Block 4 routes the
    response back here (not to Telegram).
    """
    session = await require_session(request)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    input_text = data.get("input_text", "").strip()
    if not input_text:
        return web.json_response({"error": "input_text required"}, status=400)

    conversation_id_str = data.get("conversation_id") or str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # Emit query.received to Block 13 — source_surface="dashboard" is the
    # critical field that makes Block 4 route the response back here
    event_payload = {
        "event_type": "query.received",
        "source_block": 2,
        "event_id": event_id,
        "conversation_id": conversation_id_str,
        "zone_scope": "personal",
        "payload": {
            "input_text": input_text,
            "source_surface": "dashboard",  # D-146: Block 4 egress routing
            "surface_type": "dashboard",
            "auth_metadata": {
                "surface_type": "dashboard",
                "surface_authenticated": True,
                "user_id": session["user_id"],
            },
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/events",
                json=event_payload,
                timeout=5.0,
            )
            resp.raise_for_status()
    except Exception as exc:
        log.error("dashboard_query_emit_failed", exc=str(exc))
        return web.json_response({"error": "Failed to submit query"}, status=502)

    log.info(
        "dashboard_query_submitted",
        event_id=event_id,
        conversation_id=conversation_id_str,
        user_id=session["user_id"],
    )
    return web.json_response({
        "conversation_id": conversation_id_str,
        "event_id": event_id,
        "status": "submitted",
    })


async def handle_poll_response(request: web.Request) -> web.Response:
    """GET /api/response?conversation_id=xxx — poll for query response.

    Returns the response if available, or 202 Accepted if still pending.
    Frontend polls this endpoint every 1–2 seconds until 200.

    D-147 AC-4: responses are stored in _pending_responses by push.py
    when Block 13 pushes to /push/response.
    """
    await require_session(request)

    conversation_id = request.rel_url.query.get("conversation_id", "")
    if not conversation_id:
        return web.json_response({"error": "conversation_id required"}, status=400)

    response_data = _pending_responses.pop(conversation_id, None)
    if response_data is None:
        return web.json_response({"status": "pending"}, status=202)

    return web.json_response({
        "status": "ready",
        "response_text": response_data.get("response_text", ""),
        "event_id": response_data.get("event_id", ""),
    })


async def handle_history(request: web.Request) -> web.Response:
    """POST /api/history — retrieve conversation history from Block 13.

    Body: {"conversation_id": "uuid", "limit": N (optional, default 50)}
    Returns: {"turns": [...], "conversation_id": "..."}

    D-147 AC-6: reads from the same clive_state.conversation_turns table
    as Telegram. Queries from either surface appear in this history.
    """
    await require_session(request)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    conversation_id = data.get("conversation_id", "")
    if not conversation_id:
        return web.json_response({"error": "conversation_id required"}, status=400)

    limit = int(data.get("limit", 50))

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/retrieve/conversation-history",
                json={"conversation_id": conversation_id, "limit": limit},
                timeout=5.0,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        log.error("dashboard_history_fetch_failed", exc=str(exc))
        return web.json_response({"error": "Failed to fetch history"}, status=502)

    return web.json_response(result)


async def handle_pending(request: web.Request) -> web.Response:
    """GET /api/pending — list pending Block 9 confirmation requests.

    D-147 AC-5: returns pending actions from Block 13's retrieval endpoint.
    Returns: {"actions": [...], "count": N}
    """
    await require_session(request)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/retrieve/pending-actions",
                json={"zone_scope": "personal"},
                timeout=5.0,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        log.error("dashboard_pending_fetch_failed", exc=str(exc))
        return web.json_response({"error": "Failed to fetch pending actions"}, status=502)

    return web.json_response(result)


async def handle_confirm(request: web.Request) -> web.Response:
    """POST /api/confirm/<action_request_id> — confirm a pending action.

    D-006: emits action.owner_response to Block 13 with decision='confirmed'.
    Block 9 handles the lifecycle — this does not update pending_actions directly.
    Returns: {"status": "ok"}
    """
    session = await require_session(request)
    action_request_id = request.match_info.get("action_request_id", "")

    if not action_request_id:
        return web.json_response({"error": "action_request_id required"}, status=400)

    event_payload = {
        "event_type": "action.owner_response",
        "source_block": 2,
        "event_id": str(uuid.uuid4()),
        "payload": {
            "action_request_id": action_request_id,
            "decision": "confirmed",
            "source_surface": "dashboard",
            "user_id": session["user_id"],
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/events",
                json=event_payload,
                timeout=5.0,
            )
            resp.raise_for_status()
    except Exception as exc:
        log.error("dashboard_confirm_failed", exc=str(exc), action_request_id=action_request_id)
        return web.json_response({"error": "Failed to submit confirmation"}, status=502)

    log.info("dashboard_action_confirmed", action_request_id=action_request_id)
    return web.json_response({"status": "ok", "decision": "confirmed"})


async def handle_cancel(request: web.Request) -> web.Response:
    """POST /api/cancel/<action_request_id> — cancel a pending action.

    D-006: emits action.owner_response to Block 13 with decision='rejected'.
    Block 9 handles the lifecycle.
    Returns: {"status": "ok"}
    """
    session = await require_session(request)
    action_request_id = request.match_info.get("action_request_id", "")

    if not action_request_id:
        return web.json_response({"error": "action_request_id required"}, status=400)

    event_payload = {
        "event_type": "action.owner_response",
        "source_block": 2,
        "event_id": str(uuid.uuid4()),
        "payload": {
            "action_request_id": action_request_id,
            "decision": "rejected",
            "source_surface": "dashboard",
            "user_id": session["user_id"],
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/events",
                json=event_payload,
                timeout=5.0,
            )
            resp.raise_for_status()
    except Exception as exc:
        log.error("dashboard_cancel_failed", exc=str(exc), action_request_id=action_request_id)
        return web.json_response({"error": "Failed to submit cancellation"}, status=502)

    log.info("dashboard_action_cancelled", action_request_id=action_request_id)
    return web.json_response({"status": "ok", "decision": "rejected"})
