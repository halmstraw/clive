"""Push routing — Block 13 outbound delivery to Block 8, Block 15, and Block 23."""

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
