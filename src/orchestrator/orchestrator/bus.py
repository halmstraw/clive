"""In-process event bus — Block 13 core.

D-062: in-process pub/sub, no external broker.
D-003: all inter-block communication routes through here.
D-025: at-least-once delivery via retry.
D-026: per-conversation ordering via per-conversation queues.
D-028: backpressure — reject at source when queue full, notify owner.
D-037: alignment check before every dispatch.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from . import alignment, audit
from .events.schema import AlignmentResult, CLIVEEvent
from .events.taxonomy import ALIGNMENT_REJECTED, DELIVERY_FAILED, SYSTEM_OVERRIDE_ACTIVE
from .retry import DELIVERY_FAILED as RETRY_FAILED, with_retry

log = structlog.get_logger()

# Type alias for subscriber callables
Subscriber = Callable[[CLIVEEvent], Awaitable[None]]

# Per-conversation queues for ordering guarantee (D-026)
# Key: conversation_id str | "_system" for non-conversation events
ConversationQueue = asyncio.Queue[CLIVEEvent]

MAX_QUEUE_SIZE = 100  # Backpressure threshold (D-028)


class EventBus:
    """In-process pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[int, Subscriber]]] = defaultdict(list)
        self._queues: dict[str, ConversationQueue] = {}
        self._override_active: bool = False
        self._workers: dict[str, asyncio.Task[None]] = {}

    def subscribe(self, event_type: str, block_id: int, handler: Subscriber) -> None:
        """Register a subscriber for an event type."""
        self._subscribers[event_type].append((block_id, handler))
        log.info("subscriber_registered", event_type=event_type, block_id=block_id)

    async def publish(self, event: CLIVEEvent) -> None:
        """Publish an event.

        Flow:
        1. Alignment check (synchronous, blocking) — D-037
        2. Audit log write — must succeed before dispatch
        3. Route to per-conversation queue for ordered delivery — D-026
        """
        # System override check — D-006 / system.override.issued
        if self._override_active and event.event_type != SYSTEM_OVERRIDE_ACTIVE:
            log.warning("event_held_override_active", event_id=str(event.event_id))
            return

        # 1. Alignment check
        result = alignment.check(event)
        is_pass = result in (AlignmentResult.PASS, AlignmentResult.ENHANCED_PASS)

        # 2. Audit log write (always — pass or fail)
        routing_outcome = "dispatched" if is_pass else f"rejected:{result}"
        await audit.write(event, result, routing_outcome)

        if not is_pass:
            await self._emit_rejection(event, result)
            return

        # 3. Queue for ordered delivery
        queue_key = str(event.conversation_id) if event.conversation_id else "_system"
        await self._enqueue(queue_key, event)

    async def _enqueue(self, queue_key: str, event: CLIVEEvent) -> None:
        """Place event in conversation queue. Reject if full (D-028)."""
        if queue_key not in self._queues:
            self._queues[queue_key] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
            self._workers[queue_key] = asyncio.create_task(
                self._process_queue(queue_key)
            )

        queue = self._queues[queue_key]
        if queue.full():
            log.error(
                "queue_full_backpressure",
                queue_key=queue_key,
                event_id=str(event.event_id),
            )
            # TODO: emit capacity alert to Block 4 (D-028)
            # This requires Block 4 to be operational
            return

        await queue.put(event)

    async def _process_queue(self, queue_key: str) -> None:
        """Drain a conversation queue, dispatching events in order."""
        queue = self._queues[queue_key]
        while True:
            event = await queue.get()
            await self._dispatch(event)
            queue.task_done()

    async def _dispatch(self, event: CLIVEEvent) -> None:
        """Dispatch event to all registered subscribers with retry.

        Uses RETRY_FAILED sentinel to distinguish exhausted-retries from
        void-success (push functions return None on success, which must not
        be treated as failure).
        """
        subscribers = self._subscribers.get(event.event_type, [])

        for block_id, handler in subscribers:
            result = await with_retry(
                lambda h=handler, e=event: h(e),
                event_id=str(event.event_id),
                subscriber_block=block_id,
            )
            if result is RETRY_FAILED:
                # All retries exhausted — dead-letter
                await self._emit_delivery_failed(event, block_id)

    async def _emit_rejection(self, event: CLIVEEvent, result: AlignmentResult) -> None:
        """Emit alignment.rejected event."""
        rejection = CLIVEEvent(
            event_type=ALIGNMENT_REJECTED,
            source_block=13,
            conversation_id=event.conversation_id,
            payload={
                "rejected_event_id": str(event.event_id),
                "rejected_event_type": event.event_type,
                "alignment_result": str(result),
            },
        )
        # Write to audit directly — rejection events bypass the bus to avoid recursion
        await audit.write(rejection, AlignmentResult.PASS, "emitted")
        log.warning(
            "alignment_rejected",
            rejected_event_id=str(event.event_id),
            result=str(result),
        )

    async def _emit_delivery_failed(self, event: CLIVEEvent, block_id: int) -> None:
        """Emit delivery.failed event and log dead-letter state."""
        failure = CLIVEEvent(
            event_type=DELIVERY_FAILED,
            source_block=13,
            conversation_id=event.conversation_id,
            payload={
                "failed_event_id": str(event.event_id),
                "failed_event_type": event.event_type,
                "subscriber_block": block_id,
            },
        )
        await audit.write(failure, AlignmentResult.PASS, "emitted")
        log.error(
            "delivery_failed_dead_letter",
            event_id=str(event.event_id),
            subscriber_block=block_id,
        )
        # TODO: notify owner via Block 4 when operational

    def set_override(self, active: bool) -> None:
        """Activate or deactivate system override (D-006)."""
        self._override_active = active
        log.warning("system_override", active=active)


# Module-level singleton
bus = EventBus()
