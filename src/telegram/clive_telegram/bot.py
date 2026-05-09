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
from .db import get_pool
from .session import sessions

log = structlog.get_logger()

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")

# Idempotency: track rendered event_ids to avoid duplicate renders (D-025)
_rendered_event_ids: set[str] = set()

# Telegram Application instance (set in main.py)
_app: Application | None = None

# D-079 two-step activation state: chat_id → (document_type, version_id)
# Cleared after confirmation or on a new /activate call.
_pending_activations: dict[int, tuple[str, str]] = {}

VALID_DOCUMENT_TYPES = {"personality", "alignment_rules"}


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


async def handle_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1 of D-079: /activate <document_type>.

    Looks up the pending (is_active = false) record for the given
    document_type, shows the owner the version_id and a content
    preview, then prompts for /confirm_activate <version_id>.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    args = context.args or []
    if not args or args[0] not in VALID_DOCUMENT_TYPES:
        await update.message.reply_text(
            "Usage: /activate personality\n       /activate alignment\\_rules"
        )
        return

    document_type = args[0]

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT version_id, document_content
            FROM clive_state.system_documents
            WHERE document_type = $1 AND zone_scope = 'personal' AND is_active = false
            ORDER BY created_at DESC
            LIMIT 1
            """,
            document_type,
        )

    if not row:
        await update.message.reply_text(f"No pending {document_type} document found.")
        return

    version_id = str(row["version_id"])
    preview = row["document_content"][:200]

    _pending_activations[chat_id] = (document_type, version_id)

    log.info(
        "activation_initiated",
        chat_id=chat_id,
        document_type=document_type,
        version_id=version_id,
    )

    await update.message.reply_text(
        f"Pending {document_type} document found.\n"
        f"Version: {version_id}\n\n"
        f"Preview:\n{preview}\n\n"
        f"Reply /confirm_activate {version_id} to activate."
    )


async def handle_confirm_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 2 of D-079: /confirm_activate <version_id>.

    Atomically sets is_active = true for the specified version_id and
    is_active = false for any previously active version of the same
    document_type — both updates in a single transaction.
    Emits a config.changed event to Block 13.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    pending = _pending_activations.get(chat_id)
    if not pending:
        await update.message.reply_text(
            "No pending activation. Send /activate <document_type> first."
        )
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /confirm\\_activate <version\\_id>")
        return

    confirmed_version_id = args[0]
    document_type, expected_version_id = pending

    if confirmed_version_id != expected_version_id:
        await update.message.reply_text(
            f"Version ID mismatch. Expected `{expected_version_id}`.",
            parse_mode="Markdown",
        )
        return

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Deactivate any currently active version for this document_type
                await conn.execute(
                    """
                    UPDATE clive_state.system_documents
                    SET is_active = false
                    WHERE document_type = $1 AND zone_scope = 'personal' AND is_active = true
                    """,
                    document_type,
                )
                # Activate the confirmed version
                updated = await conn.fetchval(
                    """
                    UPDATE clive_state.system_documents
                    SET is_active = true
                    WHERE version_id = $1 AND document_type = $2 AND zone_scope = 'personal'
                    RETURNING version_id
                    """,
                    uuid.UUID(confirmed_version_id),
                    document_type,
                )
                # Guard before emit — raises so asyncpg rolls back both UPDATEs.
                if not updated:
                    raise ValueError(
                        f"version_id {confirmed_version_id} not found for {document_type}"
                    )
                # Emit inside the transaction — if this raises, asyncpg rolls back
                # both UPDATEs so the document state is left unchanged (D-080).
                await _emit_to_orchestrator(
                    "config.changed",
                    {
                        "event_id": str(uuid.uuid4()),
                        "document_type": document_type,
                        "version_id": confirmed_version_id,
                        "activated_by": "owner",
                    },
                )

    except Exception as exc:
        log.error(
            "activation_failed",
            document_type=document_type,
            version_id=confirmed_version_id,
            error=str(exc),
        )
        await update.message.reply_text(
            "Activation failed — could not record to audit log. "
            "Your document was not changed. Please try again."
        )
        return

    # Clear the pending state
    _pending_activations.pop(chat_id, None)

    log.info(
        "activation_complete",
        document_type=document_type,
        version_id=confirmed_version_id,
    )

    await update.message.reply_text(
        f"Activated. {document_type} v`{confirmed_version_id}` is now live.",
        parse_mode="Markdown",
    )
