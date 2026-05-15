"""Push routing — Block 13 outbound delivery to Block 8, Block 15, and Block 23.

All push functions call raise_for_status() so HTTP 4xx/5xx responses from
downstream services are raised as exceptions and retried with backoff (D-055).

Every push function that delivers to the surface includes event_id explicitly
so Block 23's idempotency check has a stable key to work with. Omitting
event_id causes event_id="" at the surface, which poisons the idempotency
set and blocks all subsequent responses.

v0.4 (D-115): push_query_to_block8 fetches conversation history from DB and
injects it into the payload; stores user turn after successful push.
push_response_to_surface stores the assistant turn after successful push.
Failures are logged and non-fatal — query proceeds without history.

v0.6 (D-125): push_cost_cap_notification_to_surface added — routes
cost.cap_exceeded event to Block 23 as an owner alert (D-003 compliant).
"""

from __future__ import annotations

import os

import httpx
import structlog

from . import retrieval
from .events.schema import CLIVEEvent

log = structlog.get_logger()

TELEGRAM_URL = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082")
QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://query:8081")
PROCESSING_SERVICE_URL = os.environ.get("PROCESSING_SERVICE_URL", "http://processing:8083")


async def push_query_to_block8(event: CLIVEEvent) -> None:
    """Push query.received to Block 8.

    D-115: fetches conversation history before pushing, stores user turn after.
    History is injected as conversation_history in the payload.
    Memory failures are non-fatal — query proceeds without history.
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
    """Push query.response to Block 23 (Telegram surface).

    event_id is explicitly included from event.event_id — it is NOT in
    event.payload (the CLIVEEvent model puts declared fields like event_id
    on the object, not in the payload dict). Without this, deliver_response
    receives event_id="" and the idempotency cache blocks all responses
    after the first one.

    D-115: stores assistant turn after successful push.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/response",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()

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
    """Push alert.triggered to Block 23."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/alert",
            json={
                "event_id": str(event.event_id),
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def push_ingest_to_block15(event: CLIVEEvent) -> None:
    """Push ingest.received to Block 15 (processing service)."""
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
    """Push ingest.processed or ingest.rejected to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/ingest-status",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Block 9 — Action Layer push functions (v0.3)
# ---------------------------------------------------------------------------

async def push_confirmation_to_surface(event: CLIVEEvent) -> None:
    """Push action.confirmation_requested to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/action-confirmation",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def push_action_outcome_to_surface(event: CLIVEEvent) -> None:
    """Push action.rejected to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/action-outcome",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def push_confirmed_to_deletion(event: CLIVEEvent) -> None:
    """Push action.confirmed to Block 15 deletion handler."""
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
    """Push deletion.complete or deletion.not_found to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/deletion-result",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Block 20 — Cost cap notification (v0.6, D-125)
# ---------------------------------------------------------------------------

async def push_cost_cap_notification_to_surface(event: CLIVEEvent) -> None:
    """Push cost.cap_exceeded notification to Block 23 as an owner alert.

    D-003: Block 8 emits cost.cap_exceeded to Block 13 via HTTP.
    Block 13 routes here. Block 23 receives it via the /alert endpoint.
    No direct Block 8 → Block 23 communication.
    """
    today_spend = event.payload.get("today_spend_usd", 0.0)
    cap = event.payload.get("cap_usd", 0.0)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_URL}/alert",
            json={
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
            timeout=10.0,
        )
        resp.raise_for_status()
