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
