*Block 13 implementation specification — produced May 2026. All design decisions resolved. Ready for implementation.*

---
# Block 13 — Orchestrator Source Code Specification (Claude Code Input)

## Purpose

Complete implementation specification for the Block 13 Central Orchestrator. Claude Code reads this and writes the source files. All design decisions are resolved. No further design input required before coding begins.

**Decisions implemented:** D-003, D-018, D-025, D-026, D-028, D-030, D-031, D-037, D-043, D-055, D-062, D-063

**Claude Code instruction:** Create all files at the paths shown under `src/orchestrator/`. Use Python unless a compelling reason exists to deviate — consistency with the broader CLIVE stack matters more than per-service language optimisation. Commit as `feat: Block 13 orchestrator scaffold`.

---

## Repository Structure to Create

```
src/
  orchestrator/
    Dockerfile
    pyproject.toml
    orchestrator/
      __init__.py
      main.py              # Entry point — starts event bus and HTTP health server
      bus.py               # In-process pub/sub event bus (D-062)
      alignment.py         # Alignment gate — rules-and-schema check (D-037)
      audit.py             # Audit log writer — INSERT-only role (D-067)
      retry.py             # Retry logic with exponential backoff (D-055)
      retrieval.py         # Orchestrator-mediated retrieval broker (D-043)
      events/
        __init__.py
        schema.py          # Event dataclasses for all 6 event classes
        taxonomy.py        # Event type constants
      health.py            # HTTP health endpoint
    tests/
      test_bus.py
      test_alignment.py
      test_retry.py
      test_retrieval.py
```

---

## src/orchestrator/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY orchestrator/ ./orchestrator/

# Non-root user
RUN useradd -m -u 1000 clive
USER clive

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "orchestrator.main"]
```

---

## src/orchestrator/pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "clive-orchestrator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.29",        # PostgreSQL async driver for audit log writes
    "aiohttp>=3.9",         # HTTP health endpoint
    "pydantic>=2.6",        # Event schema validation
    "structlog>=24.1",      # Structured logging
    "python-dotenv>=1.0",   # Load /etc/clive/secrets.env
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## src/orchestrator/orchestrator/events/taxonomy.py

```python
"""Event type constants — Block 13 taxonomy.

All event types used in CLIVE. Grouped by class as defined in
the Block 13 requirements artefact.
"""

# Class 1 — Interaction
QUERY_RECEIVED = "query.received"
QUERY_RESPONSE = "query.response"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_REJECTED = "approval.rejected"
APPROVAL_TIMEOUT = "approval.timeout"
FEEDBACK_EXPLICIT = "feedback.explicit"
FEEDBACK_IMPLICIT = "feedback.implicit"
ACTION_REQUESTED_UNAVAILABLE = "action.requested_unavailable"

# Class 2 — Knowledge
INGESTION_TRIGGERED = "ingestion.triggered"
INGESTION_COMPLETED = "ingestion.completed"
PROCESSING_COMPLETED = "processing.completed"
RETRIEVAL_REQUESTED = "retrieval.requested"
RETRIEVAL_COMPLETED = "retrieval.completed"

# Class 3 — Action
ACTION_PROPOSED = "action.proposed"
ACTION_DISPATCHED = "action.dispatched"
ACTION_COMPLETED = "action.completed"
ACTION_FAILED = "action.failed"
ACTION_CANCELLED = "action.cancelled"

# Class 4 — Worker
WORKER_SPAWNED = "worker.spawned"
WORKER_HEARTBEAT = "worker.heartbeat"
WORKER_COMPLETED = "worker.completed"
WORKER_FAILED = "worker.failed"
WORKER_RETIRED = "worker.retired"
WORKER_HEARTBEAT_MISSED = "worker.heartbeat.missed"

# Class 5 — Evolution
VARIANT_CREATED = "variant.created"
VARIANT_EVALUATED = "variant.evaluated"
VARIANT_PROMOTED = "variant.promoted"
VARIANT_RETIRED = "variant.retired"
EVOLUTION_BOUNDARY_BREACH = "evolution.boundary.breach"

# Class 6 — System
COST_THRESHOLD_APPROACHED = "cost.threshold.approached"
COST_THRESHOLD_EXCEEDED = "cost.threshold.exceeded"
SYSTEM_HEALTH_DEGRADED = "system.health.degraded"
SYSTEM_OVERRIDE_ISSUED = "system.override.issued"
SYSTEM_OVERRIDE_ACTIVE = "system.override.active"
CONFIG_CHANGED = "config.changed"
SECURITY_ANOMALY_DETECTED = "security.anomaly.detected"

# Orchestrator-emitted
ALIGNMENT_REJECTED = "alignment.rejected"
DELIVERY_FAILED = "delivery.failed"
ALERT_TRIGGERED = "alert.triggered"
```

---

## src/orchestrator/orchestrator/events/schema.py

```python
"""Event schema — all CLIVE events are instances of CLIVEEvent.

Pydantic models for validation and serialisation.
D-025: all events carry event_id for idempotency.
D-030: bridge-origin events carry provenance metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Provenance(str, Enum):
    PRODUCTION = "production"
    BRIDGE = "bridge"  # Experimental zone origin — D-030


class CLIVEEvent(BaseModel):
    """Base event. Every inter-block communication is a CLIVEEvent."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    source_block: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    conversation_id: uuid.UUID | None = None
    zone_scope: str = "personal"  # D-050: hard-coded at v0.1
    provenance: Provenance = Provenance.PRODUCTION
    payload: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class AlignmentResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ENHANCED_PASS = "enhanced_pass"
    ENHANCED_FAIL = "enhanced_fail"
```

---

## src/orchestrator/orchestrator/alignment.py

```python
"""Block 22 alignment gate — rules-and-schema implementation.

D-037: deterministic rules, closed failure.
D-030: bridge-origin events route through enhanced gate.
D-004: goal function protection.
D-005: personality protection.

Rules are loaded from the alignment constitution document stored
in Block 16. At v0.1 they are also expressed here as code for
bootstrap — the Block 16 version takes precedence once the
system is operational.
"""

from __future__ import annotations

import structlog

from .events.schema import AlignmentResult, CLIVEEvent, Provenance
from .events.taxonomy import (
    ACTION_PROPOSED,
    EVOLUTION_BOUNDARY_BREACH,
    VARIANT_CREATED,
    VARIANT_EVALUATED,
    VARIANT_PROMOTED,
    VARIANT_RETIRED,
)

log = structlog.get_logger()

# Evolution event types that may target protected parameters
EVOLUTION_EVENT_TYPES = {
    VARIANT_CREATED,
    VARIANT_EVALUATED,
    VARIANT_PROMOTED,
    VARIANT_RETIRED,
}

# Block numbers for protected components
BLOCK_PERSONALITY = 1
BLOCK_ALIGNMENT = 22


def _check_standard(event: CLIVEEvent) -> tuple[bool, str]:
    """Standard alignment check applied to all production events.

    Returns (passed, reason). Closed failure: if any check fails,
    the event is rejected.
    """
    # Irreversible action gate — route to confirmation, not execution
    if event.event_type == ACTION_PROPOSED:
        payload = event.payload
        if payload.get("destructive", False):
            return False, "destructive_action_requires_confirmation"

    # Personality protection — D-005
    if event.event_type in EVOLUTION_EVENT_TYPES:
        target = event.payload.get("target_block")
        if target == BLOCK_PERSONALITY:
            return False, "evolution_targeting_personality_block"

    # Goal function protection — D-004
    if event.event_type in EVOLUTION_EVENT_TYPES:
        if event.payload.get("modifies_alignment_constitution", False):
            return False, "evolution_modifying_alignment_constitution"

    # Deception check — declared intent must match payload
    declared_type = event.payload.get("declared_event_type")
    if declared_type and declared_type != event.event_type:
        return False, "declared_intent_mismatch"

    # Zone boundary check
    payload_zone = event.payload.get("zone_of_origin")
    if payload_zone and payload_zone != event.zone_scope:
        # Cross-zone data without explicit permission
        if not event.payload.get("cross_zone_permitted", False):
            return False, "zone_boundary_violation"

    return True, "pass"


def _check_enhanced(event: CLIVEEvent) -> tuple[bool, str]:
    """Enhanced alignment gate for bridge-origin events — D-030.

    Superset of standard check. Stricter provenance and mutation
    boundary checks. Closed failure is absolute.
    """
    # Provenance integrity
    if event.provenance != Provenance.BRIDGE:
        return False, "enhanced_gate_called_on_non_bridge_event"

    provenance_meta = event.payload.get("provenance_metadata", {})
    if not provenance_meta.get("experimental_zone_id"):
        return False, "missing_experimental_zone_id"

    # Mutation boundary — cannot affect alignment or personality
    if event.payload.get("modifies_alignment_constitution", False):
        return False, "bridge_event_modifying_alignment_constitution"

    if event.payload.get("target_block") == BLOCK_PERSONALITY:
        return False, "bridge_event_targeting_personality"

    # Fitness signal conformance
    if event.event_type in (VARIANT_EVALUATED, VARIANT_PROMOTED):
        if "fitness_scores" not in event.payload:
            return False, "fitness_signal_missing_required_fields"

    # Novelty flag — route to owner awareness before proceeding
    if event.payload.get("novel_capability", False):
        return False, "novel_capability_requires_owner_review"

    # Run standard checks as well
    passed, reason = _check_standard(event)
    if not passed:
        return False, f"enhanced_standard_check_failed:{reason}"

    return True, "enhanced_pass"


def check(event: CLIVEEvent) -> AlignmentResult:
    """Run the appropriate alignment gate for this event.

    Bridge-origin events → enhanced gate.
    Production events → standard gate.

    Returns AlignmentResult. Never raises — closed failure means FAIL.
    """
    try:
        if event.provenance == Provenance.BRIDGE:
            passed, reason = _check_enhanced(event)
            result = AlignmentResult.ENHANCED_PASS if passed else AlignmentResult.ENHANCED_FAIL
        else:
            passed, reason = _check_standard(event)
            result = AlignmentResult.PASS if passed else AlignmentResult.FAIL

        log.info(
            "alignment_check",
            event_id=str(event.event_id),
            event_type=event.event_type,
            result=result,
            reason=reason,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        # Closed failure — any exception is treated as a rejection
        log.error(
            "alignment_check_exception",
            event_id=str(event.event_id),
            exc=str(exc),
        )
        return AlignmentResult.FAIL
```

---

## src/orchestrator/orchestrator/audit.py

```python
"""Audit log writer for Block 16.

D-067: connects as clive_audit_writer role (INSERT-only).
D-025: idempotent — duplicate event_id is acknowledged, not duplicated.
Block 13 requirement: log write must succeed before event is dispatched.
"""

from __future__ import annotations

import hashlib
import json
import os

import asyncpg
import structlog

from .events.schema import AlignmentResult, CLIVEEvent

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the audit writer connection pool.

    Uses clive_audit_writer role — INSERT only on clive_audit.event_log.
    """
    global _pool
    dsn = (
        f"postgresql://clive_audit_writer:{os.environ['AUDIT_WRITER_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    log.info("audit_pool_initialised")


async def write(event: CLIVEEvent, alignment_result: AlignmentResult, routing_outcome: str) -> None:
    """Write event to immutable audit log.

    Must be called and awaited before dispatching the event to subscribers.
    Idempotent: duplicate event_id is silently ignored (ON CONFLICT DO NOTHING).
    """
    if _pool is None:
        raise RuntimeError("Audit pool not initialised")

    payload_hash = hashlib.sha256(
        json.dumps(event.payload, sort_keys=True).encode()
    ).hexdigest()

    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_audit.event_log
              (event_id, event_type, source_block, timestamp,
               payload_hash, alignment_result, routing_outcome,
               conversation_id, zone_scope)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.event_id,
            event.event_type,
            event.source_block,
            event.timestamp,
            payload_hash,
            alignment_result.value if hasattr(alignment_result, 'value') else alignment_result,
            routing_outcome,
            event.conversation_id,
            event.zone_scope,
        )
```

---

## src/orchestrator/orchestrator/retry.py

```python
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
```

---

## src/orchestrator/orchestrator/bus.py

```python
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
from .retry import with_retry

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
        """Dispatch event to all registered subscribers with retry."""
        subscribers = self._subscribers.get(event.event_type, [])

        for block_id, handler in subscribers:
            result = await with_retry(
                lambda h=handler, e=event: h(e),
                event_id=str(event.event_id),
                subscriber_block=block_id,
            )
            if result is None:
                # Retry exhausted — dead-letter
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
```

---

## src/orchestrator/orchestrator/retrieval.py

```python
"""Orchestrator-mediated retrieval broker — D-043.

Block 8 does not call Block 16 directly (D-003).
Block 13 brokers the call as a synchronous sub-step within
the query.submitted event lifecycle.

At v0.1 this is a direct async function call to the storage
layer, logged but not a full event bus round-trip.
"""

from __future__ import annotations

import os
from typing import Any
import uuid

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the retrieval connection pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    log.info("retrieval_pool_initialised")


async def retrieve(
    retrieval_query: str,
    zone_scope: str,
    result_limit: int,
    conversation_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Retrieve relevant knowledge chunks from Block 16.

    Returns ranked_chunks list with content, source_attribution,
    relevance_score, zone_of_origin, chunk_id.

    Enforces zone boundary at query time (D-050).
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

    log.info(
        "retrieval_start",
        conversation_id=str(conversation_id),
        zone_scope=zone_scope,
        result_limit=result_limit,
    )

    async with _pool.acquire() as conn:
        # Hybrid retrieval: full-text search + vector similarity
        # Reranking applied in application code after initial fetch
        rows = await conn.fetch(
            """
            SELECT
                chunk_id,
                content,
                source_attribution,
                zone_of_origin,
                ts_rank_cd(to_tsvector('english', content),
                           plainto_tsquery('english', $1)) AS text_score,
                1 - (embedding <=> (SELECT embedding FROM clive_search.chunks
                     WHERE content = $1 LIMIT 1)) AS vector_score
            FROM clive_search.chunks
            WHERE zone_of_origin = $2
            ORDER BY text_score + vector_score DESC
            LIMIT $3
            """,
            retrieval_query,
            zone_scope,
            result_limit,
        )

    ranked_chunks = [
        {
            "chunk_id": str(row["chunk_id"]),
            "content": row["content"],
            "source_attribution": row["source_attribution"],
            "relevance_score": float(row["text_score"] + row["vector_score"]),
            "zone_of_origin": row["zone_of_origin"],
        }
        for row in rows
    ]

    log.info(
        "retrieval_complete",
        conversation_id=str(conversation_id),
        result_count=len(ranked_chunks),
    )

    return {"ranked_chunks": ranked_chunks, "result_count": len(ranked_chunks)}


async def retrieve_system_document(
    document_type: str,
    zone_scope: str,
    version_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve a system document (personality or alignment rules) by identity.

    Returns full document content, version_id, timestamp, is_active.
    """
    if _pool is None:
        raise RuntimeError("Retrieval pool not initialised")

    async with _pool.acquire() as conn:
        if version_id:
            row = await conn.fetchrow(
                """
                SELECT document_content, version_id, created_at, is_active
                FROM clive_state.system_documents
                WHERE document_type = $1 AND version_id = $2 AND zone_scope = $3
                """,
                document_type, version_id, zone_scope,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT document_content, version_id, created_at, is_active
                FROM clive_state.system_documents
                WHERE document_type = $1 AND is_active = true AND zone_scope = $2
                """,
                document_type, zone_scope,
            )

    if not row:
        raise ValueError(f"System document not found: {document_type}")

    return {
        "document_content": row["document_content"],
        "version_id": str(row["version_id"]),
        "version_timestamp": row["created_at"].isoformat(),
        "is_active": row["is_active"],
    }
```

---

## src/orchestrator/orchestrator/health.py

```python
"""HTTP health endpoint for Block 13.

Docker Compose and GitHub Actions verify deployment against this.
"""

from __future__ import annotations

from aiohttp import web


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 13})


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
```

---

## src/orchestrator/orchestrator/main.py

```python
"""Block 13 entry point.

Starts the event bus, audit pool, retrieval pool, and health server.
Runs until interrupted.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from dotenv import load_dotenv

from . import audit, retrieval
from .bus import bus
from .health import start_health_server

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def main() -> None:
    log.info("orchestrator_starting", block=13)

    # Initialise database pools
    await audit.init_pool()
    await retrieval.init_pool()

    # Start health server
    runner = await start_health_server()
    log.info("health_server_started", port=8080)

    log.info("orchestrator_ready")

    # Block until shutdown signal
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("orchestrator_shutting_down")
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## src/orchestrator/tests/test_bus.py

```python
"""Tests for in-process event bus."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.bus import EventBus
from orchestrator.events.schema import AlignmentResult, CLIVEEvent
from orchestrator.events.taxonomy import QUERY_RECEIVED, QUERY_RESPONSE


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_subscriber_receives_event(bus):
    received = []

    async def handler(event: CLIVEEvent) -> None:
        received.append(event)

    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=handler)

    with patch("orchestrator.bus.alignment.check", return_value=AlignmentResult.PASS), \
         patch("orchestrator.bus.audit.write", new_callable=AsyncMock):
        event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
        await bus.publish(event)
        # Allow queue processing
        await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].event_type == QUERY_RECEIVED


@pytest.mark.asyncio
async def test_alignment_failure_prevents_dispatch(bus):
    received = []

    async def handler(event: CLIVEEvent) -> None:
        received.append(event)

    bus.subscribe(QUERY_RECEIVED, block_id=8, handler=handler)

    with patch("orchestrator.bus.alignment.check", return_value=AlignmentResult.FAIL), \
         patch("orchestrator.bus.audit.write", new_callable=AsyncMock):
        event = CLIVEEvent(event_type=QUERY_RECEIVED, source_block=23)
        await bus.publish(event)
        await asyncio.sleep(0.05)

    assert len(received) == 0
```

---

## src/orchestrator/tests/test_alignment.py

```python
"""Tests for alignment gate."""

from orchestrator.alignment import check
from orchestrator.events.schema import AlignmentResult, CLIVEEvent, Provenance
from orchestrator.events.taxonomy import ACTION_PROPOSED, VARIANT_PROMOTED


def test_standard_pass():
    event = CLIVEEvent(event_type="query.received", source_block=23)
    assert check(event) == AlignmentResult.PASS


def test_destructive_action_rejected():
    event = CLIVEEvent(
        event_type=ACTION_PROPOSED,
        source_block=8,
        payload={"destructive": True},
    )
    assert check(event) == AlignmentResult.FAIL


def test_evolution_targeting_personality_rejected():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        payload={"target_block": 1},
    )
    assert check(event) == AlignmentResult.FAIL


def test_bridge_event_passes_enhanced_gate():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        provenance=Provenance.BRIDGE,
        payload={
            "provenance_metadata": {"experimental_zone_id": "exp-01"},
            "fitness_scores": {"accuracy": 0.9, "cost": 0.1},
        },
    )
    assert check(event) == AlignmentResult.ENHANCED_PASS


def test_bridge_event_missing_provenance_rejected():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        provenance=Provenance.BRIDGE,
        payload={},  # Missing provenance_metadata
    )
    assert check(event) == AlignmentResult.ENHANCED_FAIL
```

---

## SQL additions — infrastructure/sql/init/05_application_tables.sql

Add to a new file `infrastructure/sql/init/05_application_tables.sql`:

```sql
-- Knowledge chunks (Block 16 search index)
CREATE TABLE IF NOT EXISTS clive_search.chunks (
    chunk_id         uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_id      uuid        NOT NULL,
    content          text        NOT NULL,
    embedding        vector(1536),  -- Adjust dimensions to match embedding model
    source_attribution text      NOT NULL,
    zone_of_origin   text        NOT NULL DEFAULT 'personal',
    position         integer     NOT NULL,
    metadata         jsonb       NOT NULL DEFAULT '{}',
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_zone ON clive_search.chunks (zone_of_origin);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON clive_search.chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON clive_search.chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- System documents (personality, alignment rules) — Block 16
CREATE TABLE IF NOT EXISTS clive_state.system_documents (
    id               uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_type    text        NOT NULL CHECK (document_type IN ('personality', 'alignment_rules')),
    version_id       uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_content text        NOT NULL,
    zone_scope       text        NOT NULL DEFAULT 'personal',
    is_active        boolean     NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    UNIQUE (document_type, version_id)
);

-- Enforce: exactly one active version per document type
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_docs_active
    ON clive_state.system_documents (document_type)
    WHERE is_active = true;

-- Orchestrator state (retry tracking, subscriber registry, dead-letter)
CREATE TABLE IF NOT EXISTS clive_state.orchestrator_state (
    key   text NOT NULL PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

GRANT ALL ON clive_search.chunks TO clive_app;
GRANT ALL ON clive_state.system_documents TO clive_app;
GRANT ALL ON clive_state.orchestrator_state TO clive_app;
```

---

*Block 13 source code specification — Architect from Infrastructure Agent spec and Block 13 requirements artefact*
*May 2026. Claude Code: commit as `feat: Block 13 orchestrator scaffold`.*
*After committing, write Block 8 query service next.*
