"""Retry logic for event delivery.

D-055: 5 retries, 2s initial backoff, x2 multiplier.
D-031: after exhaustion, event enters dead-letter state and owner is notified.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

log = structlog.get_logger()

MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds
BACKOFF_MULTIPLIER = 2.0

T = TypeVar("T")


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    event_id: str,
    subscriber_block: int,
) -> T | None:
    """Attempt fn up to MAX_RETRIES times with exponential backoff.

    Returns the result on success. Returns None and logs dead-letter
    state on exhaustion.
    """
    backoff = INITIAL_BACKOFF

    for attempt in range(1, MAX_RETRIES + 2):  # +1 for initial attempt
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            if attempt > MAX_RETRIES:
                log.error(
                    "delivery_exhausted",
                    event_id=event_id,
                    subscriber_block=subscriber_block,
                    attempts=MAX_RETRIES + 1,
                    exc=str(exc),
                )
                return None  # Caller handles dead-letter notification

            log.warning(
                "delivery_retry",
                event_id=event_id,
                subscriber_block=subscriber_block,
                attempt=attempt,
                backoff=backoff,
                exc=str(exc),
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 64.0)  # ~60s ceiling

    return None  # unreachable but satisfies type checker
