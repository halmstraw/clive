"""Conversation session identity management.

D-018: Block 23 is stateless — conversation_id is carried in event
payloads, not held in Block 23 local state.

Telegram threads map naturally to conversation_ids:
- A new private message from the owner starts or continues a session.
- Thread ID (message_id of first message) is used as a stable session key
  within a Telegram conversation context.
- For simplicity at v0.1, each bot restart uses a new conversation_id.
  Persistent session continuity across restarts is a post-v0.1 concern.

The conversation_id is a UUID generated per session and carried in
every event payload emitted by Block 23.
"""

from __future__ import annotations

import uuid


class SessionManager:
    """Maps Telegram chat_id to active conversation_id.

    In-process only — intentionally not persisted (D-018 at v0.1).
    Post-v0.1: conversation_id recovery from Block 16.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, uuid.UUID] = {}

    def get_or_create(self, chat_id: int) -> uuid.UUID:
        """Return existing conversation_id or create a new one."""
        if chat_id not in self._sessions:
            self._sessions[chat_id] = uuid.uuid4()
        return self._sessions[chat_id]

    def reset(self, chat_id: int) -> uuid.UUID:
        """Start a new conversation for this chat_id."""
        self._sessions[chat_id] = uuid.uuid4()
        return self._sessions[chat_id]


# Module-level singleton
sessions = SessionManager()
