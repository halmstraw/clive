"""Telegram bot handler — Block 23 core.

Inbound path (D-058):
  Telegram message → auth check → attach auth metadata
  → emit query.received to Block 13

Outbound path:
  Block 13 pushes query.response to Block 23's HTTP endpoint
  → render to Telegram

Block 23 owns everything from owner input to event emission.
Block 4 owns response formatting — at v0.1 on the same surface,
Block 23 handles basic rendering until the Experience Agent
designs Block 4's rendering contract.

D-025: idempotent on duplicate query.response (same event_id
not re-rendered).
D-028: system notification events rendered as plain messages.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .auth import is_authenticated, make_auth_metadata
from .session import sessions

log = structlog.get_logger()

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")

# Idempotency: track rendered event_ids to avoid duplicate renders (D-025)
_rendered_event_ids: set[str] = set()

# Telegram Application instance (set in main.py)
_app: Application | None = None


def set_app(app: Application) -> None:
    global _app
    _app = app


async def _emit_to_orchestrator(event_type: str, payload: dict[str, Any]) -> None:
    """Submit event to Block 13 via HTTP (D-003)."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ORCHESTRATOR_URL}/events",
            json={
                "event_type": event_type,
                "source_block": 23,
                **payload,
            },
            timeout=10.0,
        )
        response.raise_for_status()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inbound Telegram message from owner.

    D-057: authenticate via channel membership.
    D-058: attach surface auth metadata.
    D-050: carry zone_scope = 'personal'.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    # D-057: channel-as-authentication
    if not is_authenticated(chat_id):
        return  # Silent ignore — not the owner

    user_input = update.message.text or ""
    if not user_input.strip():
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    log.info(
        "message_received",
        chat_id=chat_id,
        conversation_id=str(conversation_id),
        event_id=str(event_id),
    )

    # Emit query.received with auth metadata attached (D-058)
    await _emit_to_orchestrator(
        "query.received",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "zone_scope": "personal",  # D-050
            "input_text": user_input,
            "timestamp": update.message.date.isoformat(),
            "surface_type": "telegram",
            "auth_metadata": make_auth_metadata(chat_id),  # D-058
        },
    )


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — reset conversation."""
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    conversation_id = sessions.reset(chat_id)
    log.info("conversation_reset", chat_id=chat_id, conversation_id=str(conversation_id))

    if update.message:
        await update.message.reply_text("Ready.")


async def deliver_response(response_payload: dict[str, Any], chat_id: int) -> None:
    """Deliver query.response to the owner via Telegram.

    Called by the HTTP endpoint that Block 13 pushes responses to.
    D-025: idempotent — duplicate event_id not re-rendered.
    """
    event_id = response_payload.get("event_id", "")

    if event_id in _rendered_event_ids:
        log.info("idempotency_skip_render", event_id=event_id)
        return

    _rendered_event_ids.add(event_id)

    response_text = response_payload.get("response_text", "")
    confidence = response_payload.get("confidence", {})

    # Append low-confidence indicator if retrieval was poor (D-047)
    if not confidence.get("threshold_met", True) and confidence.get("chunks_returned", 1) == 0:
        response_text += "\n\n⚠️ _(Answered from general knowledge — no relevant documents found)_"

    if _app:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=response_text,
            parse_mode="Markdown",
        )
        log.info("response_delivered", event_id=event_id, chat_id=chat_id)


async def deliver_alert(alert_payload: dict[str, Any], chat_id: int) -> None:
    """Deliver system alert to the owner (D-028, D-073)."""
    severity = alert_payload.get("severity", "info")
    title = alert_payload.get("title", "System alert")
    body = alert_payload.get("body", "")

    severity_emoji = {"info": "ℹ️", "warn": "⚠️", "error": "🔴"}.get(severity, "ℹ️")
    text = f"{severity_emoji} *{title}*\n{body}"

    if _app:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
