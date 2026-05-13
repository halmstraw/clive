*Block 8 implementation specification — produced May 2026. All design decisions resolved. Ready for implementation.*

---
# Block 8 — Query Service Source Code Specification (Claude Code Input)

## Purpose

Complete implementation specification for the Block 8 Query/RAG service. Claude Code reads this and writes the source files. All design decisions are resolved.

**Decisions implemented:** D-035, D-039, D-043, D-044, D-045, D-046, D-047, D-048, D-051, D-052, D-053, D-062, D-077

**Claude Code instruction:** Create all files under `src/query/`. Commit as `feat: Block 8 query service scaffold`.

---

## Repository Structure to Create

```
src/
  query/
    Dockerfile
    pyproject.toml
    query/
      __init__.py
      main.py           # Entry point — subscribes to query.received, starts event bus subscriber
      handler.py        # Core query handler — context assembly, LLM call, response emission
      context.py        # Token budget and context assembly (D-044)
      llm.py            # LiteLLM wrapper (D-077)
      idempotency.py    # Per-conversation response cache (D-046)
    tests/
      test_context.py
      test_handler.py
      test_idempotency.py
```

---

## src/query/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY query/ ./query/

RUN useradd -m -u 1000 clive
USER clive

CMD ["python", "-m", "query.main"]
```

---

## src/query/pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "clive-query"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "litellm>=1.35",         # LLM abstraction layer — D-077
    "asyncpg>=0.29",         # PostgreSQL for orchestrator pub/sub
    "pydantic>=2.6",
    "structlog>=24.1",
    "python-dotenv>=1.0",
    "httpx>=0.27",           # HTTP client for orchestrator event submission
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

## src/query/query/idempotency.py

```python
"""Per-conversation response cache for idempotency.

D-046: cache response keyed by event_id, conversation-scoped.
Duplicate query.received with same event_id returns cached response.
Cache is in-process memory, cleared when conversation ends.
"""

from __future__ import annotations

import uuid
from typing import Any


class IdempotencyCache:
    """In-process cache: event_id → response payload."""

    def __init__(self) -> None:
        # {conversation_id: {event_id: response_payload}}
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    def get(self, conversation_id: uuid.UUID, event_id: uuid.UUID) -> dict[str, Any] | None:
        conv = self._store.get(str(conversation_id), {})
        return conv.get(str(event_id))

    def set(
        self,
        conversation_id: uuid.UUID,
        event_id: uuid.UUID,
        response: dict[str, Any],
    ) -> None:
        key = str(conversation_id)
        if key not in self._store:
            self._store[key] = {}
        self._store[key][str(event_id)] = response

    def clear_conversation(self, conversation_id: uuid.UUID) -> None:
        self._store.pop(str(conversation_id), None)


# Module-level singleton
cache = IdempotencyCache()
```

---

## src/query/query/context.py

```python
"""Context window assembly for Block 8.

D-044: dynamic allocation with priority ordering.
  Tier 1: personality document (always present, takes what it needs)
  Tier 2: alignment rules (always present, takes what it needs)
  Tier 3: conversation history (minimum guaranteed, surplus if available)
  Tier 4: retrieved knowledge chunks (minimum guaranteed, surplus if available)

Token budget values are conservative defaults. Adjust based on
actual document sizes once personality and alignment docs are loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Total token budget for LLM context
# Default: 100k tokens (Claude Sonnet supports 200k)
# Reserved: ~2k for the query itself and response overhead
TOTAL_BUDGET = 98_000

# Tier 3 and 4 minimum guarantees (tokens)
MIN_HISTORY_TOKENS = 2_000
MIN_RETRIEVAL_TOKENS = 4_000

# Approximate tokens per character (rough estimate; real count uses tiktoken)
CHARS_PER_TOKEN = 4


@dataclass
class AssembledContext:
    personality: str
    alignment_rules: str
    conversation_history: list[dict[str, str]]
    retrieved_chunks: list[dict[str, Any]]
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _chunks_to_text(chunks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[Source: {c['source_attribution']}]\n{c['content']}"
        for c in chunks
    )


def assemble(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
) -> AssembledContext:
    """Assemble context respecting D-044 priority ordering.

    Tiers 1 and 2 always included in full.
    Remaining budget split between tiers 3 and 4 with minimums.
    Surplus flows to whichever tier has more content.
    """
    # Fixed costs (Tiers 1 and 2)
    personality_tokens = _estimate_tokens(personality)
    alignment_tokens = _estimate_tokens(alignment_rules)
    fixed_cost = personality_tokens + alignment_tokens

    remaining = TOTAL_BUDGET - fixed_cost
    if remaining < MIN_HISTORY_TOKENS + MIN_RETRIEVAL_TOKENS:
        # Pathological case: personality/alignment docs are enormous
        # Include minimums only and truncate if needed
        remaining = MIN_HISTORY_TOKENS + MIN_RETRIEVAL_TOKENS

    # Calculate available for Tier 3 and 4
    history_text = _format_history(conversation_history)
    chunks_text = _chunks_to_text(retrieved_chunks)

    history_tokens_needed = _estimate_tokens(history_text)
    chunks_tokens_needed = _estimate_tokens(chunks_text)

    # Allocate with minimums and surplus flow
    surplus = remaining - MIN_HISTORY_TOKENS - MIN_RETRIEVAL_TOKENS
    surplus = max(0, surplus)

    history_surplus = max(0, history_tokens_needed - MIN_HISTORY_TOKENS)
    chunks_surplus = max(0, chunks_tokens_needed - MIN_RETRIEVAL_TOKENS)
    total_surplus_needed = history_surplus + chunks_surplus

    if total_surplus_needed > 0:
        history_alloc = MIN_HISTORY_TOKENS + int(
            surplus * history_surplus / total_surplus_needed
        )
        chunks_alloc = remaining - history_alloc
    else:
        history_alloc = MIN_HISTORY_TOKENS
        chunks_alloc = remaining - history_alloc

    # Truncate to allocation
    final_history = _truncate_history(conversation_history, history_alloc)
    final_chunks = _truncate_chunks(retrieved_chunks, chunks_alloc)

    total_estimate = fixed_cost + history_alloc + chunks_alloc

    return AssembledContext(
        personality=personality,
        alignment_rules=alignment_rules,
        conversation_history=final_history,
        retrieved_chunks=final_chunks,
        token_estimate=total_estimate,
    )


def _format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in history)


def _truncate_history(
    history: list[dict[str, str]], token_budget: int
) -> list[dict[str, str]]:
    """Keep most recent messages that fit within budget."""
    result = []
    tokens_used = 0
    for msg in reversed(history):
        msg_tokens = _estimate_tokens(msg["content"])
        if tokens_used + msg_tokens > token_budget:
            break
        result.insert(0, msg)
        tokens_used += msg_tokens
    return result


def _truncate_chunks(
    chunks: list[dict[str, Any]], token_budget: int
) -> list[dict[str, Any]]:
    """Include highest-relevance chunks that fit within budget."""
    result = []
    tokens_used = 0
    for chunk in chunks:  # Already sorted by relevance
        chunk_tokens = _estimate_tokens(chunk["content"])
        if tokens_used + chunk_tokens > token_budget:
            break
        result.append(chunk)
        tokens_used += chunk_tokens
    return result
```

---

## src/query/query/llm.py

```python
"""LiteLLM wrapper for Block 8.

D-077: provider abstracted via LiteLLM. Default provider is Anthropic.
Provider and model are configuration values, not code changes.

CLIVE_LLM_MODEL env var controls the model.
Examples:
  anthropic/claude-sonnet-4-6   (default)
  openai/gpt-4o
  anthropic/claude-opus-4-5
"""

from __future__ import annotations

import os
from typing import Any

import litellm
import structlog

log = structlog.get_logger()

DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"


def get_model() -> str:
    return os.environ.get("CLIVE_LLM_MODEL", DEFAULT_MODEL)


async def complete(
    personality: str,
    alignment_rules: str,
    conversation_history: list[dict[str, str]],
    retrieved_chunks: list[dict[str, Any]],
    user_query: str,
) -> str:
    """Call LLM with assembled context. Returns response text.

    Context structure (D-044 priority order):
      System prompt = personality (Tier 1) + alignment rules (Tier 2)
      Messages = conversation history (Tier 3) + current query with
                 retrieved context prepended (Tier 4)
    """
    model = get_model()

    system_prompt = f"{personality}\n\n---\n\n{alignment_rules}"

    # Prepend retrieved context to the current user query
    if retrieved_chunks:
        context_text = "\n\n".join(
            f"[Source: {c['source_attribution']}]\n{c['content']}"
            for c in retrieved_chunks
        )
        augmented_query = (
            f"Relevant context from your knowledge base:\n\n{context_text}"
            f"\n\n---\n\nQuery: {user_query}"
        )
    else:
        augmented_query = user_query

    messages = [
        *conversation_history,
        {"role": "user", "content": augmented_query},
    ]

    log.info("llm_call_start", model=model, history_turns=len(conversation_history))

    response = await litellm.acompletion(
        model=model,
        system=system_prompt,
        messages=messages,
        max_tokens=2048,
    )

    text = response.choices[0].message.content
    log.info("llm_call_complete", model=model, response_chars=len(text))
    return text
```

---

## src/query/query/handler.py

```python
"""Core query handler for Block 8.

Receives query.received event, assembles context, calls LLM,
emits query.response. Handles action-intent queries (D-045).
Idempotent via response cache (D-046).
Confidence signal is retrieval quality only (D-047).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

from . import context as ctx
from . import llm
from .idempotency import cache

log = structlog.get_logger()

# Action-intent keywords — simple heuristic for v0.1
# Evolves post-v0.1 via Block 21
ACTION_VERBS = {
    "send", "email", "message", "book", "schedule", "create",
    "delete", "update", "post", "call", "order", "buy", "pay",
    "remind", "set", "add", "remove", "cancel", "upload",
}

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")


async def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Submit event to Block 13 via HTTP.

    At v0.1, Block 8 and Block 13 communicate via the in-process
    bus in the orchestrator container. Block 8 is a separate container
    and submits events via HTTP to Block 13's event intake endpoint.
    Block 13 then routes via its internal bus.
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ORCHESTRATOR_URL}/events",
            json={"event_type": event_type, "source_block": 8, **payload},
            timeout=10.0,
        )


def _detect_action_intent(text: str) -> str | None:
    """Heuristic: detect if query implies an action CLIVE cannot perform.

    Returns the detected action verb or None.
    """
    words = text.lower().split()
    for word in words:
        if word in ACTION_VERBS:
            return word
    return None


def _compute_confidence(
    ranked_chunks: list[dict[str, Any]],
    relevance_threshold: float = 0.3,
) -> dict[str, Any]:
    """Compute retrieval quality confidence signal — D-047."""
    chunk_count = len(ranked_chunks)
    max_score = max((c["relevance_score"] for c in ranked_chunks), default=0.0)
    threshold_met = max_score >= relevance_threshold
    return {
        "chunks_returned": chunk_count,
        "highest_relevance_score": max_score,
        "threshold_met": threshold_met,
    }


async def handle_query(event: dict[str, Any]) -> None:
    """Handle a query.received event.

    1. Check idempotency cache (D-046)
    2. Retrieve knowledge via orchestrator (D-043)
    3. Check for action intent (D-045)
    4. Assemble context (D-044)
    5. Call LLM (D-077)
    6. Emit query.response
    """
    event_id = uuid.UUID(event["event_id"])
    conversation_id = uuid.UUID(event["conversation_id"])
    user_input = event["input_text"]
    zone_scope = event.get("zone_scope", "personal")

    # 1. Idempotency check — D-046
    cached = cache.get(conversation_id, event_id)
    if cached:
        log.info("idempotency_cache_hit", event_id=str(event_id))
        await _emit_event("query.response", {**cached, "conversation_id": str(conversation_id)})
        return

    # 2. Check for action intent — D-045
    action_verb = _detect_action_intent(user_input)
    if action_verb:
        log.info("action_intent_detected", verb=action_verb)
        await _emit_event(
            "action.requested_unavailable",
            {
                "conversation_id": str(conversation_id),
                "event_id": str(event_id),
                "recognised_action_type": action_verb,
                "original_query_context": user_input,
            },
        )
        # Still respond — acknowledge and offer what we can do
        response_text = (
            f"I can see you want to {action_verb} something — "
            "actions aren't available yet. I can answer questions "
            "and search my knowledge base. What would you like to know?"
        )
        response_payload = {
            "event_id": str(event_id),
            "response_text": response_text,
            "confidence": {"chunks_returned": 0, "highest_relevance_score": 0.0, "threshold_met": False},
        }
        cache.set(conversation_id, event_id, response_payload)
        await _emit_event("query.response", {**response_payload, "conversation_id": str(conversation_id)})
        return

    # 3. Retrieve system documents via orchestrator (D-043, D-048)
    async with httpx.AsyncClient() as client:
        personality_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/system-document",
            json={"document_type": "personality", "zone_scope": zone_scope},
            timeout=10.0,
        )
        personality_resp.raise_for_status()
        personality_doc = personality_resp.json()["document_content"]

        alignment_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/system-document",
            json={"document_type": "alignment_rules", "zone_scope": zone_scope},
            timeout=10.0,
        )
        alignment_resp.raise_for_status()
        alignment_doc = alignment_resp.json()["document_content"]

    # 4. Retrieve knowledge chunks via orchestrator (D-043)
    async with httpx.AsyncClient() as client:
        retrieval_resp = await client.post(
            f"{ORCHESTRATOR_URL}/retrieve/knowledge",
            json={
                "retrieval_query": user_input,
                "zone_scope": zone_scope,
                "result_limit": 20,
                "conversation_id": str(conversation_id),
            },
            timeout=15.0,
        )
        retrieval_resp.raise_for_status()
        retrieval_result = retrieval_resp.json()

    ranked_chunks = retrieval_result.get("ranked_chunks", [])
    confidence = _compute_confidence(ranked_chunks)

    # 5. Retrieve conversation history from event payload
    conversation_history = event.get("conversation_history", [])

    # 6. Assemble context (D-044)
    assembled = ctx.assemble(
        personality=personality_doc,
        alignment_rules=alignment_doc,
        conversation_history=conversation_history,
        retrieved_chunks=ranked_chunks,
    )

    # 7. Call LLM (D-077)
    response_text = await llm.complete(
        personality=assembled.personality,
        alignment_rules=assembled.alignment_rules,
        conversation_history=assembled.conversation_history,
        retrieved_chunks=assembled.retrieved_chunks,
        user_query=user_input,
    )

    # 8. Build response and cache it
    response_payload = {
        "event_id": str(event_id),
        "response_text": response_text,
        "confidence": confidence,
    }
    cache.set(conversation_id, event_id, response_payload)

    # 9. Emit query.response
    await _emit_event(
        "query.response",
        {**response_payload, "conversation_id": str(conversation_id)},
    )

    log.info(
        "query_handled",
        event_id=str(event_id),
        chunks_used=len(assembled.retrieved_chunks),
        threshold_met=confidence["threshold_met"],
    )
```

---

## src/query/query/main.py

```python
"""Block 8 entry point.

At v0.1 Block 8 runs as a separate container. Block 13 pushes
query.received events to Block 8 via HTTP POST to /query endpoint.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv

from .handler import handle_query

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def handle_query_endpoint(request: web.Request) -> web.Response:
    """Receive query.received events from Block 13."""
    event = await request.json()
    asyncio.create_task(handle_query(event))
    return web.json_response({"status": "accepted"})


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 8})


async def main() -> None:
    log.info("query_service_starting", block=8)

    app = web.Application()
    app.router.add_post("/query", handle_query_endpoint)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()

    log.info("query_service_ready", port=8081)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## src/query/tests/test_context.py

```python
"""Tests for context assembly."""

from query.context import assemble

PERSONALITY = "You are CLIVE." * 10
ALIGNMENT = "Rule 1: No fabrication." * 5


def test_assemble_basic():
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=[{"role": "user", "content": "Hello"}],
        retrieved_chunks=[{"content": "Fact A", "source_attribution": "doc1", "relevance_score": 0.9}],
    )
    assert result.personality == PERSONALITY
    assert result.alignment_rules == ALIGNMENT
    assert len(result.conversation_history) >= 1
    assert len(result.retrieved_chunks) >= 1
    assert result.token_estimate > 0


def test_assemble_no_chunks():
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=[],
        retrieved_chunks=[],
    )
    assert result.retrieved_chunks == []
    assert result.conversation_history == []


def test_history_truncation():
    long_history = [{"role": "user", "content": "x" * 500}] * 50
    result = assemble(
        personality=PERSONALITY,
        alignment_rules=ALIGNMENT,
        conversation_history=long_history,
        retrieved_chunks=[],
    )
    # Should not include all 50 messages — truncated to budget
    assert len(result.conversation_history) < 50
```

---

## src/query/tests/test_idempotency.py

```python
"""Tests for idempotency cache."""

import uuid
from query.idempotency import IdempotencyCache


def test_cache_miss_returns_none():
    c = IdempotencyCache()
    assert c.get(uuid.uuid4(), uuid.uuid4()) is None


def test_cache_hit_returns_stored():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt = uuid.uuid4()
    response = {"response_text": "Hello", "event_id": str(evt)}
    c.set(conv, evt, response)
    assert c.get(conv, evt) == response


def test_different_event_ids_independent():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt1, evt2 = uuid.uuid4(), uuid.uuid4()
    c.set(conv, evt1, {"response_text": "A"})
    assert c.get(conv, evt2) is None


def test_clear_conversation():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt = uuid.uuid4()
    c.set(conv, evt, {"response_text": "A"})
    c.clear_conversation(conv)
    assert c.get(conv, evt) is None
```

---

## Compose addition — docker-compose.yml

Add the `query` service to `infrastructure/compose/docker-compose.yml`:

```yaml
query:
  image: ghcr.io/clive-owner/clive-query:${QUERY_IMAGE_TAG:-latest}
  container_name: clive-query
  restart: always
  env_file: /etc/clive/secrets.env
  environment:
    - CLIVE_ENV=production
    - ORCHESTRATOR_URL=http://orchestrator:8080
    - CLIVE_LLM_MODEL=anthropic/claude-sonnet-4-6
  depends_on:
    orchestrator:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
  networks:
    - clive-internal
```

Also add `QUERY_IMAGE_TAG=latest` to `infrastructure/compose/.env.example`.

---

## Block 13 additions needed

Block 13's `main.py` needs HTTP endpoints that Block 8 calls. Add to `src/orchestrator/orchestrator/health.py` (or a new `routes.py`):

```python
from aiohttp import web
from .bus import bus
from .events.schema import CLIVEEvent
from .retrieval import retrieve, retrieve_system_document

async def handle_event_intake(request: web.Request) -> web.Response:
    data = await request.json()
    event = CLIVEEvent(**data)
    await bus.publish(event)
    return web.json_response({"status": "accepted"})

async def handle_retrieve_knowledge(request: web.Request) -> web.Response:
    data = await request.json()
    result = await retrieve(
        retrieval_query=data["retrieval_query"],
        zone_scope=data["zone_scope"],
        result_limit=data.get("result_limit", 20),
        conversation_id=data.get("conversation_id"),
    )
    return web.json_response(result)

async def handle_retrieve_system_document(request: web.Request) -> web.Response:
    data = await request.json()
    result = await retrieve_system_document(
        document_type=data["document_type"],
        zone_scope=data["zone_scope"],
        version_id=data.get("version_id"),
    )
    return web.json_response(result)
```

Register in the aiohttp app:

```python
app.router.add_post("/events", handle_event_intake)
app.router.add_post("/retrieve/knowledge", handle_retrieve_knowledge)
app.router.add_post("/retrieve/system-document", handle_retrieve_system_document)
```

Also add a subscriber in Block 13 startup to push `query.received` events to Block 8:

```python
import os, httpx
from .events.taxonomy import QUERY_RECEIVED

QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://query:8081")

async def push_query_to_block8(event: CLIVEEvent) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{QUERY_SERVICE_URL}/query",
            json={**event.payload, "event_id": str(event.event_id),
                  "conversation_id": str(event.conversation_id)},
            timeout=10.0,
        )

bus.subscribe(QUERY_RECEIVED, block_id=8, handler=push_query_to_block8)
```

Add `QUERY_SERVICE_URL=http://query:8081` to `.env.example` and orchestrator environment.

---

*Block 8 source code specification — Architect*
*May 2026. Claude Code: commit as `feat: Block 8 query service scaffold`.*
*After committing, write Block 23 Telegram surface next.*
