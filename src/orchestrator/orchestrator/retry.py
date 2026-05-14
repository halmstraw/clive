"""Retry logic for event delivery.

D-055: 5 retries, 2s initial backoff, x2 multiplier.
D-031: after exhaustion, event enters dead-letter state and owner is notified.

SENTINEL: with_retry returns _DELIVERY_FAILED (a private sentinel object) when
all retries are exhausted.  The bus checks against this sentinel — not against
None — so that void push functions (which return None on success) are not
mistakenly treated as failures.
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

# Sentinel returned by with_retry when all attempts are exhausted.
# Distinct from None so void push functions (return None on success) are not
# misidentified as delivery failures by the bus.
class _FailureSentinel:
    """Returned by with_retry when delivery is exhausted after all retries."""
    __slots__ = ()

DELIVERY_FAILED = _FailureSentinel()


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    event_id: str,
    subscriber_block: int,
) -> T | _FailureSentinel:
    """Attempt fn up to MAX_RETRIES times with exponential backoff.

    Returns the result on success (None for void functions).
    Returns DELIVERY_FAILED sentinel on exhaustion.
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
                return DELIVERY_FAILED

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

    return DELIVERY_FAILED  # unreachable but satisfies type checker
