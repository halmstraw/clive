"""Channel-as-authentication for Block 23.

D-057: the Telegram channel is the authentication factor.
D-058: Block 23 attaches surface authentication metadata to
       inbound events before they reach Block 13.

At v0.1, authentication is: is the message from the owner's
Telegram chat ID? The owner's chat ID is set as an environment
variable at deploy time. Any message not from this chat ID is
silently ignored.
"""

from __future__ import annotations

import os

import structlog

log = structlog.get_logger()


def get_owner_chat_id() -> int:
    """Return the owner's Telegram chat ID from environment."""
    raw = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not raw:
        raise RuntimeError("TELEGRAM_OWNER_CHAT_ID not set")
    return int(raw)


def is_authenticated(chat_id: int) -> bool:
    """Return True if message is from the owner's chat.

    D-057: channel membership is the authentication factor.
    D-001: single owner — one chat ID is the complete auth model at v0.1.
    """
    owner_id = get_owner_chat_id()
    authenticated = chat_id == owner_id
    if not authenticated:
        log.warning("unauthenticated_message", chat_id=chat_id)
    return authenticated


def make_auth_metadata(chat_id: int) -> dict:
    """Build surface authentication metadata attached to outbound events.

    D-058: Block 23 attaches this; Block 13 enforces it.
    """
    return {
        "surface_type": "telegram",
        "surface_authenticated": True,
        "channel_id": str(chat_id),
    }
