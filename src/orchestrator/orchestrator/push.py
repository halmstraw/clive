"""Push routing — Block 13 outbound delivery to Block 8, Block 15, and Block 23.

v0.3: added Block 9 action layer push functions:
  push_confirmation_to_surface     — action.confirmation_requested → Block 23
  push_action_outcome_to_surface   — action.rejected → Block 23
  push_confirmed_to_deletion       — action.confirmed → Block 15 deletion handler
  push_deletion_result_to_surface  — deletion.complete / deletion.not_found → Block 23
"""

from __future__ import annotations

import os

import httpx
import structlog

from .events.schema import CLIVEEvent

log = structlog.get_logger()

TELEGRAM_URL = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082")
QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://query:8081")
PROCESSING_SERVICE_URL = os.environ.get("PROCESSING_SERVICE_URL", "http://processing:8083")


async def push_query_to_block8(event: CLIVEEvent) -> None:
    """Push query.received to Block 8."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{QUERY_SERVICE_URL}/query",
            json={
                **event.payload,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id),
            },
            timeout=10.0,
        )


async def push_response_to_surface(event: CLIVEEvent) -> None:
    """Push query.response to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/response",
            json=event.payload,
            timeout=10.0,
        )


async def push_alert_to_surface(event: CLIVEEvent) -> None:
    """Push alert.triggered to Block 23."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/alert",
            json=event.payload,
            timeout=10.0,
        )


async def push_ingest_to_block15(event: CLIVEEvent) -> None:
    """Push ingest.received to Block 15 (processing service)."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{PROCESSING_SERVICE_URL}/ingest",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )


async def push_ingest_status_to_surface(event: CLIVEEvent) -> None:
    """Push ingest.processed or ingest.rejected to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/ingest-status",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )


# ---------------------------------------------------------------------------
# Block 9 — Action Layer push functions (v0.3)
# ---------------------------------------------------------------------------

async def push_confirmation_to_surface(event: CLIVEEvent) -> None:
    """Push action.confirmation_requested to Block 23 (Telegram surface).

    Block 23 uses this to send the confirmation prompt to the owner and
    store the pending action_request_id for the /confirm_delete response.
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/action-confirmation",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )


async def push_action_outcome_to_surface(event: CLIVEEvent) -> None:
    """Push action.rejected to Block 23 (Telegram surface).

    Notifies the owner that a deletion was cancelled, timed out, or not found.
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/action-outcome",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )


async def push_confirmed_to_deletion(event: CLIVEEvent) -> None:
    """Push action.confirmed to Block 15 deletion handler.

    Block 15's /delete endpoint executes the deletion and emits
    deletion.complete or deletion.not_found back to Block 13.
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{PROCESSING_SERVICE_URL}/delete",
            json={
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=30.0,
        )


async def push_deletion_result_to_surface(event: CLIVEEvent) -> None:
    """Push deletion.complete or deletion.not_found to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/deletion-result",
            json={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                **event.payload,
            },
            timeout=10.0,
        )
