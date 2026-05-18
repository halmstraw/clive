"""Push routing — Block 13 outbound delivery via Block 4 egress (D-146).

All push functions use egress.push_to_surface() or egress.push_to_all_surfaces()
— no file outside egress.py hardcodes surface URLs (D-147 AC-7).

Surface routing logic:
  QUERY_RESPONSE → source surface only (source_surface from payload, default 'telegram')
  ALERT          → all surfaces (broadcast)
  CONFIRMATION   → all surfaces (owner can confirm from any surface)
  ACTION_OUTCOME → all surfaces (feedback visible on all surfaces)
  DELETION       → all surfaces
  INGEST         → telegram only (ingestion is Telegram-only in v0.11)
  ADMIN_TOOL     → all surfaces

Block 8 (query) and Block 15 (processing) are internal services, not surfaces.
push_query_to_block8 and push_ingest_to_block15 call them directly via HTTP
(not via egress) — egress is for surface delivery only.

All push functions call raise_for_status() so HTTP 4xx/5xx responses from
downstream services are raised as exceptions and retried with backoff (D-055).

Every push function that delivers to a surface includes event_id explicitly
so surfaces' idempotency check has a stable key to work with.

v0.4 (D-115): push_query_to_block8 fetches conversation history from DB and
injects it into the payload; stores user turn after successful push.
push_response_to_surface stores the assistant turn after successful push.
Failures are logged and non-fatal — query proceeds without history.

v0.6 (D-125): push_cost_cap_notification_to_surface added.

v0.8 (D-137): push_admin_tool_result_to_surface added.

v0.11 (D-146): push.py refactored to use egress.py (Block 4).
Source-surface routing added for QUERY_RESPONSE.
Broadcast pattern for alerts, confirmations, outcomes, and deletion results.
"""

from __future__ import annotations

import os

import httpx
import structlog

from . import egress, retrieval
from .events.schema import CLIVEEvent

log = structlog.get_logger()

QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://query:8081")  # NOSONAR
PROCESSING_SERVICE_URL = os.environ.get("PROCESSING_SERVICE_URL", "http://processing:8083")  # NOSONAR

ALERT_ENDPOINT = "/alert"


async def push_query_to_block8(event: CLIVEEvent) -> None:
    """Push query.received to Block 8 (internal service — not a surface).

    D-115: fetches conversation history before pushing, stores user turn after.
    History is injected as conversation_history in the payload.
    Memory failures are non-fatal — query proceeds without history.

    D-146: source_surface is forwarded in the payload so Block 8 can include
    it in the query.response event, enabling Block 4 to route the response
    back to the originating surface.
    """
    conversation_id = event.conversation_id
    user_input = event.payload.get("input_text", "")

    # Fetch previous turns (before adding the current one)
    history: list[dict[str, str]] = []
    if conversation_id:
        try:
            history = await retrieval.get_conversation_history(conversation_id)
        except Exception as exc:
            log.warning("memory_fetch_failed", error=str(exc))

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QUERY_SERVICE_URL}/query",
            json={
                **event.payload,
                "event_id": str(event.event_id),
                "conversation_id": str(conversation_id),
                "conversation_history": history,
            },
            timeout=10.0,
        )
        resp.raise_for_status()

    # Store user turn after successful push (idempotent on event_id + role)
    if conversation_id and user_input:
        try:
            await retrieval.store_conversation_turn(
                event_id=event.event_id,
                conversation_id=conversation_id,
                role="user",
                content=user_input,
            )
        except Exception as exc:
            log.warning("memory_store_failed", role="user", error=str(exc))


async def push_response_to_surface(event: CLIVEEvent) -> None:
    """Push query.response to the originating surface via Block 4 egress.

    D-146: source_surface in payload determines the target surface.
    Default is 'telegram' for backwards compatibility with pre-v0.11 events.

    D-115: stores assistant turn after successful push.
    """
    source_surface = event.payload.get("source_surface", "telegram")

    await egress.push_to_surface(
        source_surface,
        "/response",
        {
            "event_id": str(event.event_id),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            **event.payload,
        },
    )

    # Store assistant turn after successful push (idempotent on event_id + role)
    response_text = event.payload.get("response_text", "")
    if event.conversation_id and response_text:
        try:
            await retrieval.store_conversation_turn(
                event_id=event.event_id,
                conversation_id=event.conversation_id,
                role="assistant",
                content=response_text,
            )
        except Exception as exc:
            log.warning("memory_store_failed", role="assistant", error=str(exc))


async def push_alert_to_surface(event: CLIVEEvent) -> None:
    """Push alert.triggered to all surfaces (broadcast, D-146)."""
    await egress.push_to_all_surfaces(
        ALERT_ENDPOINT,
        {
            "event_id": str(event.event_id),
            **event.payload,
        },
    )


async def push_ingest_to_block15(event: CLIVEEvent) -> None:
    """Push ingest.received to Block 15 (processing — internal service)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PROCESSING_SERVICE_URL}/ingest",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def push_ingest_status_to_surface(event: CLIVEEvent) -> None:
    """Push ingest.processed or ingest.rejected to Telegram only.

    Ingestion is Telegram-only in v0.11 — dashboard does not expose ingest.
    """
    await egress.push_to_surface(
        "telegram",
        "/ingest-status",
        {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            **event.payload,
        },
    )


# ---------------------------------------------------------------------------
# Block 9 — Action Layer push functions (v0.3, extended v0.11)
# ---------------------------------------------------------------------------

async def push_confirmation_to_surface(event: CLIVEEvent) -> None:
    """Push action.confirmation_requested to all surfaces (broadcast, D-147 AC-5).

    Owner can confirm or cancel from any surface.
    D-006 is preserved — confirmation must be explicit from the owner.
    Broadcast means both surfaces show the pending action.
    """
    await egress.push_to_all_surfaces(
        "/action-confirmation",
        {
            "event_id": str(event.event_id),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            **event.payload,
        },
    )


async def push_action_outcome_to_surface(event: CLIVEEvent) -> None:
    """Push action.rejected to all surfaces (broadcast)."""
    await egress.push_to_all_surfaces(
        "/action-outcome",
        {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            **event.payload,
        },
    )


async def push_confirmed_to_deletion(event: CLIVEEvent) -> None:
    """Push action.confirmed to Block 15 deletion handler (internal service)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PROCESSING_SERVICE_URL}/delete",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=30.0,
        )
        resp.raise_for_status()


async def push_deletion_result_to_surface(event: CLIVEEvent) -> None:
    """Push deletion.complete or deletion.not_found to all surfaces."""
    await egress.push_to_all_surfaces(
        "/deletion-result",
        {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            **event.payload,
        },
    )


# ---------------------------------------------------------------------------
# Block 20 — Cost cap notification (v0.6, D-125)
# ---------------------------------------------------------------------------

async def push_cost_cap_notification_to_surface(event: CLIVEEvent) -> None:
    """Push cost.cap_exceeded notification to all surfaces.

    D-003: Block 8 emits cost.cap_exceeded to Block 13 via HTTP.
    Block 13 routes here via Block 4 egress. No direct Block 8 → surface call.
    """
    today_spend = event.payload.get("today_spend_usd", 0.0)
    cap = event.payload.get("cap_usd", 0.0)

    await egress.push_to_all_surfaces(
        ALERT_ENDPOINT,
        {
            "event_id": str(event.event_id),
            "severity": "warn",
            "title": "Daily spend cap reached",
            "body": (
                f"Daily LLM spend cap of ${cap:.4f} reached "
                f"(today: ${today_spend:.4f}). "
                "CLIVE will not make further LLM calls today. "
                "Cap resets at midnight UTC."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Block 17 / Block 19 — Tool registry admin notifications (v0.8, D-137)
# ---------------------------------------------------------------------------

async def push_admin_tool_result_to_surface(event: CLIVEEvent) -> None:
    """Push admin.tool_updated or admin.tool_error to all surfaces.

    D-003: Block 13 emits these after processing admin.tool_disable /
    admin.tool_enable. Surfaces receive them via the /alert endpoint.
    """
    if event.event_type == "admin.tool_updated":
        tool_name = event.payload.get("tool_name", "")
        action = event.payload.get("action", "")
        title = f"Tool {action}"
        body = f"Tool '{tool_name}' {action} successfully."
        severity = "info"
    else:  # admin.tool_error
        tool_name = event.payload.get("tool_name", "")
        reason = event.payload.get("reason", "unknown")
        title = "Tool admin error"
        body = f"Tool admin error for '{tool_name}': {reason}."
        severity = "warn"

    await egress.push_to_all_surfaces(
        ALERT_ENDPOINT,
        {
            "event_id": str(event.event_id),
            "severity": severity,
            "title": title,
            "body": body,
        },
    )
