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

v0.3 additions:
  /delete <filename>      — T8 deletion, triggers Block 9 confirmation gate
  /confirm_delete         — owner confirms pending deletion
  /cancel_delete          — owner cancels pending deletion
  /bad                    — Block 18: tag most recent retrieval as poor quality
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
from .minio_client import upload_document
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

# Block 9 — pending delete confirmation state: chat_id → action_request_id
# Set when Block 13 pushes action.confirmation_requested.
# Cleared on /confirm_delete, /cancel_delete, or timeout notification.
_pending_deletes: dict[int, str] = {}

# Block 18 — last retrieval per chat_id: chat_id → {event_id, chunk_ids, conversation_id}
# Updated each time a query.response is delivered.
# Used by /bad to tag the most recent retrieval.
_last_retrieval: dict[int, dict[str, Any]] = {}

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
            "zone_scope": "personal",
            "payload": {
                "input_text": user_input,
                "timestamp": update.message.date.isoformat(),
                "surface_type": "telegram",
                "auth_metadata": make_auth_metadata(chat_id),
            },
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
    v0.3: stores last_retrieval for Block 18 /bad command.

    Attempts Markdown rendering first. Falls back to plain text if Telegram
    rejects the message (unbalanced * _ [ from LLM output). Both outcomes
    are logged so silent drops are visible in container logs.
    """
    event_id = response_payload.get("event_id", "")

    if event_id in _rendered_event_ids:
        log.info("idempotency_skip_render", event_id=event_id)
        return

    _rendered_event_ids.add(event_id)

    response_text = response_payload.get("response_text", "")
    confidence = response_payload.get("confidence", {})
    chunk_ids = response_payload.get("chunk_ids", [])

    # Store last retrieval context for Block 18 (v0.3)
    conversation_id = response_payload.get("conversation_id")
    _last_retrieval[chat_id] = {
        "event_id": event_id,
        "chunk_ids": chunk_ids,
        "conversation_id": conversation_id,
    }

    # Append low-confidence indicator if retrieval was poor (D-047)
    if not confidence.get("threshold_met", True) and confidence.get("chunks_returned", 1) == 0:
        response_text += "\n\n⚠️ (Answered from general knowledge — no relevant documents found)"

    if not _app:
        log.warning("response_drop_no_app", event_id=event_id)
        return

    # Try Markdown first; fall back to plain text on parse failure.
    # LLM responses may contain characters that break Telegram Markdown
    # (unbalanced *, _, [). Failure here was previously a silent drop.
    try:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=response_text,
            parse_mode="Markdown",
        )
        log.info("response_delivered", event_id=event_id, chat_id=chat_id)
    except Exception as exc:
        log.warning(
            "response_markdown_failed_retrying_plain",
            event_id=event_id,
            chat_id=chat_id,
            exc=str(exc),
        )
        try:
            await _app.bot.send_message(chat_id=chat_id, text=response_text)
            log.info("response_delivered_plain", event_id=event_id, chat_id=chat_id)
        except Exception as exc2:
            log.error(
                "response_delivery_failed",
                event_id=event_id,
                chat_id=chat_id,
                exc=str(exc2),
            )


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


MAX_INGEST_BYTES = 10 * 1024 * 1024  # 10 MB — D-098


async def handle_ingest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ingest caption command — D-101.

    Owner sends a document with /ingest as the caption.  File and command
    arrive in a single message; no conversational state required.

    Flow:
      1. Validate file size (D-098)
      2. Download file bytes from Telegram
      3. Upload to MinIO clive-raw-store bucket (MINIO_RAW_BUCKET)
      4. Emit ingest.received to Block 13
      5. Reply with immediate acknowledgement
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    document = update.message.document
    if not document:
        await update.message.reply_text(
            "Send a file with /ingest as the caption to ingest a document."
        )
        return

    # D-098: size check before download
    if document.file_size and document.file_size > MAX_INGEST_BYTES:
        log.warning(
            "ingest_rejected_too_large",
            chat_id=chat_id,
            file_name=document.file_name,
            file_size=document.file_size,
        )
        event_id = uuid.uuid4()
        await _emit_to_orchestrator(
            "ingest.rejected",
            {
                "event_id": str(event_id),
                "payload": {
                    "source_key": document.file_name or "unknown",
                    "reason": "file_too_large",
                    "file_size": document.file_size,
                    "chat_id": chat_id,                  # D-103 criterion 6 provenance
                },
            },
        )
        await update.message.reply_text(
            f"File too large ({document.file_size // (1024 * 1024)} MB). Maximum is 10 MB."
        )
        return

    # Download file bytes
    tg_file = await context.bot.get_file(document.file_id)
    raw_bytes = bytes(await tg_file.download_as_bytearray())

    # Build a unique object key: uuid/original-filename
    original_name = document.file_name or "document"
    source_key = f"{uuid.uuid4()}/{original_name}"
    content_type = document.mime_type or "application/octet-stream"

    try:
        await upload_document(source_key, raw_bytes, content_type)
    except RuntimeError as exc:
        log.error("minio_upload_failed", source_key=source_key, error=str(exc))
        await update.message.reply_text(
            "Could not store the file. Check that the MinIO clive-raw-store bucket exists."
        )
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    log.info(
        "ingest_received",
        chat_id=chat_id,
        source_key=source_key,
        event_id=str(event_id),
    )

    await _emit_to_orchestrator(
        "ingest.received",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "zone_scope": "personal",
            "payload": {
                "source_key": source_key,
                "original_filename": original_name,
                "file_size": document.file_size,
                "content_type": content_type,
                "chat_id": chat_id,                      # D-103 criterion 6 provenance
            },
        },
    )

    # D-099 criterion 1: immediate acknowledgement
    await update.message.reply_text(
        f"Received {original_name}. Processing — I will follow up when done."
    )


async def deliver_ingest_status(status_payload: dict[str, Any], chat_id: int) -> None:
    """Deliver ingest.processed or ingest.rejected follow-up to owner.

    Called by the HTTP endpoint that Block 13 pushes ingest status events to.
    D-099 criterion 1: owner receives follow-up with chunk count on completion.
    """
    event_type = status_payload.get("event_type", "")
    source_key = status_payload.get("source_key", "")

    if event_type == "ingest.processed":
        chunk_count = status_payload.get("chunk_count", 0)
        inserted = status_payload.get("inserted_count", chunk_count)
        filename = source_key.split("/", 1)[-1] if "/" in source_key else source_key
        text = f"Done. {filename} ingested — {inserted} new chunk(s) stored."
        if inserted < chunk_count:
            text += f" ({chunk_count - inserted} duplicate chunk(s) skipped.)"
    elif event_type == "ingest.rejected":
        reason = status_payload.get("reason", "unknown")
        filename = source_key.split("/", 1)[-1] if "/" in source_key else source_key
        reason_text = {
            "file_too_large": "file too large",
            "extraction_failed": "text extraction failed",
            "fetch_failed": "could not fetch from storage",
            "no_chunks_produced": "no content found in document",
            "embedding_failed": "embedding failed — check OPENAI_API_KEY in secrets",
            "chunk_write_failed": "failed to write to database",
        }.get(reason, reason)
        text = f"Ingestion failed for {filename}: {reason_text}."
    else:
        return

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info("ingest_status_delivered", event_type=event_type, chat_id=chat_id)


# ---------------------------------------------------------------------------
# T8 — Deletion commands (v0.3, D-006, D-109)
# ---------------------------------------------------------------------------

async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete <filename> command (D-109).

    Looks up the document by filename in clive_search.chunks.
    If not found: replies with clear not-found message (D-106 criterion 4).
    If found: emits action.pending to Block 13 → Block 9 confirmation gate.
    Block 9 will push action.confirmation_requested back → handle_action_confirmation_push.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /delete <filename>\nExample: /delete report.pdf"
        )
        return

    filename = " ".join(args).strip()
    conversation_id = sessions.get_or_create(chat_id)

    # Look up document by filename in Block 16 via the orchestrator retrieval endpoint
    # We use a direct DB lookup here via the orchestrator's lookup endpoint (D-043 pattern)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/retrieve/document-by-filename",
                json={"filename": filename, "zone_scope": "personal"},
                timeout=10.0,
            )
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await update.message.reply_text(
                    f"No document named {filename} found."
                )
                return
            log.error("delete_lookup_failed", filename=filename, error=str(exc))
            await update.message.reply_text("Could not look up the document. Please try again.")
            return
        except Exception as exc:
            log.error("delete_lookup_failed", filename=filename, error=str(exc))
            await update.message.reply_text("Could not look up the document. Please try again.")
            return

    source_keys = result.get("source_keys", [])
    if not source_keys:
        await update.message.reply_text(f"No document named {filename} found.")
        return

    # Build human-readable description for Block 9 confirmation message
    chunk_count = result.get("chunk_count", 0)
    if len(source_keys) == 1:
        description = f"Delete {filename} ({chunk_count} chunk(s))."
    else:
        description = (
            f"Delete {filename} — {len(source_keys)} version(s), {chunk_count} chunk(s) total."
        )

    event_id = uuid.uuid4()
    await _emit_to_orchestrator(
        "action.pending",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "payload": {
                "action_type": "document.delete",
                "action_target": filename,
                "action_description": description,
                "chat_id": chat_id,
            },
        },
    )

    log.info(
        "delete_action_pending",
        chat_id=chat_id,
        filename=filename,
        source_keys_count=len(source_keys),
    )
    # Block 9 will push back action.confirmation_requested — handled by
    # handle_action_confirmation_push HTTP endpoint in main.py


async def handle_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /confirm_delete — owner confirms pending deletion.

    Emits action.owner_response with confirmed=True to Block 13 → Block 9.
    Block 9 will emit action.confirmed → deletion handler.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    action_request_id = _pending_deletes.get(chat_id)
    if not action_request_id:
        await update.message.reply_text(
            "No pending deletion to confirm. Send /delete <filename> first."
        )
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        "action.owner_response",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "payload": {
                "action_request_id": action_request_id,
                "confirmed": True,
                "chat_id": chat_id,
            },
        },
    )

    # Clear pending state immediately — Block 9 is now responsible
    _pending_deletes.pop(chat_id, None)

    log.info(
        "delete_confirmed_by_owner",
        chat_id=chat_id,
        action_request_id=action_request_id,
    )
    await update.message.reply_text("Confirmed. Deleting...")


async def handle_cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel_delete — owner cancels pending deletion.

    Emits action.owner_response with confirmed=False to Block 13 → Block 9.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    action_request_id = _pending_deletes.pop(chat_id, None)
    if not action_request_id:
        await update.message.reply_text("No pending deletion to cancel.")
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        "action.owner_response",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "payload": {
                "action_request_id": action_request_id,
                "confirmed": False,
                "chat_id": chat_id,
            },
        },
    )

    log.info(
        "delete_cancelled_by_owner",
        chat_id=chat_id,
        action_request_id=action_request_id,
    )
    await update.message.reply_text("Deletion cancelled.")


async def deliver_action_confirmation(confirmation_payload: dict[str, Any], chat_id: int) -> None:
    """Receive action.confirmation_requested from Block 13 and prompt the owner.

    Stores the action_request_id so /confirm_delete and /cancel_delete can
    reference it. Sends confirmation prompt to the owner.
    """
    action_request_id = confirmation_payload.get("action_request_id", "")
    action_description = confirmation_payload.get("action_description", "")

    # Store for /confirm_delete / /cancel_delete
    _pending_deletes[chat_id] = action_request_id

    text = (
        f"⚠️ {action_description}\n\n"
        "Reply /confirm_delete to proceed or /cancel_delete to abort.\n"
        "(No response within 2 minutes cancels automatically.)"
    )

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info(
            "confirmation_prompt_sent",
            chat_id=chat_id,
            action_request_id=action_request_id,
        )


async def deliver_action_outcome(outcome_payload: dict[str, Any], chat_id: int) -> None:
    """Receive action.rejected from Block 13 and notify the owner.

    Clears the pending delete state regardless of reason.
    """
    reason = outcome_payload.get("reason", "unknown")
    action_type = outcome_payload.get("action_type", "")
    action_target = outcome_payload.get("action_target", "")

    # Clear pending state in case it's still set
    _pending_deletes.pop(chat_id, None)

    reason_text = {
        "owner_rejected": "cancelled",
        "timed_out": "timed out — no response received",
        "not_found": "the document was not found",
    }.get(reason, reason)

    if action_type == "document.delete":
        text = f"Deletion of {action_target} {reason_text}."
    else:
        text = f"Action {reason_text}."

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info(
            "action_outcome_delivered",
            chat_id=chat_id,
            reason=reason,
        )


async def deliver_deletion_result(result_payload: dict[str, Any], chat_id: int) -> None:
    """Receive deletion.complete or deletion.not_found from Block 13 and notify owner."""
    event_type = result_payload.get("event_type", "")
    filename = result_payload.get("filename", "")
    chunks_removed = result_payload.get("chunks_removed", 0)

    if event_type == "deletion.complete":
        text = f"Deleted. {filename} removed ({chunks_removed} chunk(s) purged)."
    elif event_type == "deletion.not_found":
        text = f"No document named {filename} found."
    else:
        return

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info(
            "deletion_result_delivered",
            chat_id=chat_id,
            event_type=event_type,
            filename=filename,
        )


# ---------------------------------------------------------------------------
# Block 18 — Feedback command (v0.3, D-100)
# ---------------------------------------------------------------------------

async def handle_bad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/bad — tag most recent retrieval as poor quality (Block 18).

    Looks up the last retrieval stored in _last_retrieval[chat_id].
    Writes a feedback record to clive_state.feedback.
    Emits feedback.explicit to Block 13 for audit (D-067).
    Acknowledges with a brief confirmation.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    last = _last_retrieval.get(chat_id)
    if not last:
        await update.message.reply_text(
            "No recent retrieval to tag. Send a query first."
        )
        return

    retrieval_event_id = last.get("event_id", "")
    chunk_ids = last.get("chunk_ids", [])
    conversation_id_str = last.get("conversation_id")

    if not retrieval_event_id:
        await update.message.reply_text(
            "No recent retrieval to tag. Send a query first."
        )
        return

    # Write feedback record to Block 16 (clive_state.feedback)
    pool = get_pool()
    feedback_id = uuid.uuid4()
    try:
        import json  # noqa: PLC0415
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clive_state.feedback
                    (feedback_id, retrieval_event_id, conversation_id,
                     owner_chat_id, feedback_type, submitted_at, chunk_ids)
                VALUES ($1, $2, $3, $4, 'poor_quality', now(), $5::jsonb)
                """,
                feedback_id,
                uuid.UUID(retrieval_event_id),
                uuid.UUID(conversation_id_str) if conversation_id_str else None,
                chat_id,
                json.dumps(chunk_ids),
            )
    except Exception as exc:
        log.error(
            "feedback_write_failed",
            chat_id=chat_id,
            retrieval_event_id=retrieval_event_id,
            error=str(exc),
        )
        await update.message.reply_text(
            "Could not record feedback. Please try again."
        )
        return

    # Emit feedback.explicit to Block 13 for audit (D-067)
    conversation_id = sessions.get_or_create(chat_id)
    await _emit_to_orchestrator(
        "feedback.explicit",
        {
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(conversation_id),
            "payload": {
                "feedback_id": str(feedback_id),
                "retrieval_event_id": retrieval_event_id,
                "feedback_type": "poor_quality",
                "chat_id": chat_id,
                "chunk_ids": chunk_ids,
            },
        },
    )

    log.info(
        "feedback_recorded",
        chat_id=chat_id,
        feedback_id=str(feedback_id),
        retrieval_event_id=retrieval_event_id,
    )

    await update.message.reply_text("Noted. Tagged as poor quality.")
