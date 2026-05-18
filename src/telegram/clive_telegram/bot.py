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

v0.7 additions:
  intent detection in handle_message for web.search and reminder.schedule
  /confirm_action         — generic confirm for non-delete action types
  /cancel_action          — generic cancel for non-delete action types

v0.8 additions:
  /tools                  — list all registered tools (D-137)
  /tool_disable <name>    — disable a tool (D-006 confirmation gate)
  /tool_enable <name>     — enable a tool (D-006 confirmation gate)
  /help                   — list available commands (D-119)

v0.10 additions:
  /whoami                 — show caller's user profile and zone access (D-144)
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import uuid
from typing import Any

import httpx
import structlog
from dateutil import parser as dateutil_parser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import auth
from .auth import is_authenticated, make_auth_metadata
from .db import get_pool
from .minio_client import upload_document
from .metrics import rate_limited_total, telegram_commands_total
from .session import sessions


# ---------------------------------------------------------------------------
# v0.7 — Action intent detection patterns
# ---------------------------------------------------------------------------

_SEARCH_RE = re.compile(
    r"^(?:search(?:\s+(?:for|the\s+web\s+for|online\s+for))?|look\s+up|find(?:\s+online)?)"
    r"\s+(.+)$",
    re.IGNORECASE,
)

_REMIND_PREFIX_RE = re.compile(
    r"^remind\s+me\s+(?:about|to)\s+",
    re.IGNORECASE,
)


def _get_tz() -> ZoneInfo:
    tz_name = os.environ.get("CLIVE_TIMEZONE", "UTC")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def detect_search_intent(text: str) -> str | None:
    """Return the search query if text matches a web search intent, else None."""
    m = _SEARCH_RE.match(text.strip())
    return m.group(1).strip() if m else None


def detect_reminder_intent(text: str) -> tuple[str, datetime] | None:
    """Return (message, fire_at) if text matches a reminder intent, else None.

    Uses CLIVE_TIMEZONE env var for timezone-aware parsing (option B+C).
    Returns None if the time string cannot be parsed.
    """
    text = text.strip()
    m = _REMIND_PREFIX_RE.match(text)
    if not m:
        return None
    rest = text[m.end():]
    idx = rest.lower().rfind(" at ")
    if idx == -1:
        return None
    reminder_msg = rest[:idx].strip()
    time_str = rest[idx + 4:].strip()
    tz = _get_tz()

    try:
        default_dt = datetime.now(tz)
        fire_at = dateutil_parser.parse(time_str, default=default_dt, fuzzy=True)
        if fire_at.tzinfo is None:
            fire_at = fire_at.replace(tzinfo=tz)
        return reminder_msg, fire_at
    except (ValueError, OverflowError):
        return None

log = structlog.get_logger()

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")  # NOSONAR — Docker-internal, no TLS

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

# Block 9 v0.7 — generic pending action state: chat_id → action_request_id
# Used for web.search and reminder.schedule action types.
# Cleared on /confirm_action, /cancel_action, or timeout notification.
_pending_action_generic: dict[int, str] = {}

# Block 18 — last retrieval per chat_id: chat_id → {event_id, chunk_ids, conversation_id}
# Updated each time a query.response is delivered.
# Used by /bad to tag the most recent retrieval.
_last_retrieval: dict[int, dict[str, Any]] = {}

# v0.8 — Block 17 tool management pending state.
# Set when the owner triggers /tool_disable or /tool_enable awaiting confirmation.
# Cleared on /confirm_action (moved to _confirmed_tool_ops) or /cancel_action.
_pending_tool_ops: dict[int, dict] = {}

# v0.8 — confirmed tool op awaiting admin.tool_updated push-back from Block 13.
# Populated when /confirm_action is pressed for a tool op.
# Cleared when admin.tool_updated arrives at the HTTP endpoint.
_confirmed_tool_ops: dict[int, dict] = {}

VALID_DOCUMENT_TYPES = {"personality", "alignment_rules"}

_ACTION_DOCUMENT_DELETE = "document.delete"
_EVENT_OWNER_RESPONSE = "action.owner_response"
_SUPPRESS_TELEGRAM_REASON = "suppress_telegram=True in payload"


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


async def _emit_action_pending(
    action_type: str,
    action_target: str,
    action_description: str,
    conversation_id: uuid.UUID,
    chat_id: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit action.pending for any action type (D-006, D-003)."""
    event_id = uuid.uuid4()
    payload: dict[str, Any] = {
        "action_type": action_type,
        "action_target": action_target,
        "action_description": action_description,
        "chat_id": chat_id,
    }
    if extra:
        payload.update(extra)

    await _emit_to_orchestrator(
        "action.pending",
        {
            "event_id": str(event_id),
            "conversation_id": str(conversation_id),
            "payload": payload,
        },
    )
    log.info(
        "action_pending_emitted",
        action_type=action_type,
        action_target=action_target,
        chat_id=chat_id,
    )


async def _check_rate_limit(chat_id: int, update: Update) -> bool:
    """Apply inbound rate limiting (D-125). Returns True if the message should be dropped."""
    rate_limit = int(os.environ.get("RATE_LIMIT_QUERIES_PER_HOUR", "0") or "0")
    if rate_limit <= 0:
        return False

    current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if _rate_limit_state["hour"] != current_hour:
        _rate_limit_state["hour"] = current_hour
        _rate_limit_state["count"] = 0

    if _rate_limit_state["count"] >= rate_limit:
        rate_limited_total.inc()
        log.info("rate_limit_hit", chat_id=chat_id, count=_rate_limit_state["count"])
        if update.message:
            await update.message.reply_text(
                "Rate limit reached for this hour. Please try again next hour."
            )
        return True

    _rate_limit_state["count"] += 1
    return False


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

    if await _check_rate_limit(chat_id, update):
        return

    telegram_commands_total.labels(command="query").inc()

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

    # v0.7 — Intent detection: web search or reminder take priority over query.received
    search_query = detect_search_intent(user_input)
    if search_query is not None:
        await _emit_action_pending(
            action_type="web.search",
            action_target=search_query,
            action_description=f"Search the web for: {search_query}",
            conversation_id=conversation_id,
            chat_id=chat_id,
        )
        return

    reminder_result = detect_reminder_intent(user_input)
    if reminder_result is not None:
        reminder_msg, fire_at = reminder_result
        display_time = fire_at.strftime("%Y-%m-%d %H:%M %Z").strip()
        await _emit_action_pending(
            action_type="reminder.schedule",
            action_target=reminder_msg,
            action_description=f"Schedule reminder: \"{reminder_msg}\" at {display_time}",
            conversation_id=conversation_id,
            chat_id=chat_id,
            extra={"reminder_message": reminder_msg, "fire_at": fire_at.isoformat()},
        )
        return

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
                "source_surface": "telegram",  # D-146: Block 4 egress routing
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

    telegram_commands_total.labels(command="other").inc()

    conversation_id = sessions.reset(chat_id)
    log.info("conversation_reset", chat_id=chat_id, conversation_id=str(conversation_id))

    if update.message:
        await update.message.reply_text("Ready.")


async def _send_message(chat_id: int, text: str, parse_mode: str | None) -> None:
    """Send a single Telegram message with the given parse mode."""
    kwargs: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    await _app.bot.send_message(**kwargs)  # type: ignore[union-attr]


async def _deliver_message_with_fallback(chat_id: int, text: str, event_id: str) -> bool:
    """Try Markdown then plain text, each with one network retry. Returns True on success."""
    for parse_mode in ("Markdown", None):
        for network_attempt in range(2):
            try:
                await _send_message(chat_id, text, parse_mode)
                label = "response_delivered" if parse_mode else "response_delivered_plain"
                log.info(label, event_id=event_id, chat_id=chat_id)
                return True
            except Exception as exc:
                exc_str = str(exc)
                is_network = "NetworkError" in type(exc).__name__ or "NetworkError" in exc_str
                if is_network and network_attempt == 0:
                    log.warning(
                        "response_network_error_retrying",
                        event_id=event_id,
                        chat_id=chat_id,
                        attempt=network_attempt + 1,
                        exc=exc_str,
                    )
                    await asyncio.sleep(3)
                    continue
                log.warning(
                    "response_send_failed",
                    event_id=event_id,
                    chat_id=chat_id,
                    parse_mode=parse_mode,
                    exc=exc_str,
                )
                break
    return False


async def deliver_response(response_payload: dict[str, Any], chat_id: int) -> None:
    """Deliver query.response to the owner via Telegram.

    Called by the HTTP endpoint that Block 13 pushes responses to.
    D-025: idempotent — duplicate event_id not re-rendered.
    v0.3: stores last_retrieval for Block 18 /bad command.

    Idempotency guard: only applies when event_id is non-empty. An empty
    event_id (caused by push_response_to_surface omitting it from the
    payload) must not be added to _rendered_event_ids — it would block
    every subsequent response for the lifetime of the process.

    Delivery: tries Markdown first, falls back to plain text on parse
    failure, retries once on NetworkError before logging a hard failure.
    """
    event_id = response_payload.get("event_id", "")

    if event_id:
        if event_id in _rendered_event_ids:
            log.info("idempotency_skip_render", event_id=event_id)
            return
        _rendered_event_ids.add(event_id)
    else:
        # event_id missing from payload — log and continue without idempotency
        log.warning("response_missing_event_id", chat_id=chat_id)

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

    if not await _deliver_message_with_fallback(chat_id, response_text, event_id):
        log.error("response_delivery_failed_all_attempts", event_id=event_id, chat_id=chat_id)


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

    telegram_commands_total.labels(command="other").inc()

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

    telegram_commands_total.labels(command="other").inc()

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

    telegram_commands_total.labels(command="ingest").inc()

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

    telegram_commands_total.labels(command="delete").inc()

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
                "action_type": _ACTION_DOCUMENT_DELETE,
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

    telegram_commands_total.labels(command="delete").inc()

    action_request_id = _pending_deletes.get(chat_id)
    if not action_request_id:
        await update.message.reply_text(
            "No pending deletion to confirm. Send /delete <filename> first."
        )
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        _EVENT_OWNER_RESPONSE,
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

    telegram_commands_total.labels(command="delete").inc()

    action_request_id = _pending_deletes.pop(chat_id, None)
    if not action_request_id:
        await update.message.reply_text("No pending deletion to cancel.")
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        _EVENT_OWNER_RESPONSE,
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

    Routes to the correct pending dict and shows appropriate confirm/cancel commands
    based on action_type (v0.7: document.delete keeps specific commands; all other
    types use generic /confirm_action / /cancel_action).

    suppress_telegram: if True in the payload, skips the Telegram send.
    """
    if confirmation_payload.get("suppress_telegram"):
        log.info("suppress_telegram_confirmation", reason=_SUPPRESS_TELEGRAM_REASON)
        return

    action_request_id = confirmation_payload.get("action_request_id", "")
    action_description = confirmation_payload.get("action_description", "")
    action_type = confirmation_payload.get("action_type", "")

    if action_type == _ACTION_DOCUMENT_DELETE:
        _pending_deletes[chat_id] = action_request_id
        confirm_cmd = "/confirm_delete"
        cancel_cmd = "/cancel_delete"
    else:
        _pending_action_generic[chat_id] = action_request_id
        confirm_cmd = "/confirm_action"
        cancel_cmd = "/cancel_action"

    text = (
        f"⚠️ {action_description}\n\n"
        f"Reply {confirm_cmd} to proceed or {cancel_cmd} to abort.\n"
        "(No response within 2 minutes cancels automatically.)"
    )

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info(
            "confirmation_prompt_sent",
            chat_id=chat_id,
            action_type=action_type,
            action_request_id=action_request_id,
        )


async def deliver_action_outcome(outcome_payload: dict[str, Any], chat_id: int) -> None:
    """Receive action.rejected from Block 13 and notify the owner.

    Clears pending state for all action types regardless of reason.

    suppress_telegram: if True in the payload, skips the Telegram send.
    """
    # Clear pending state for all action types
    _pending_deletes.pop(chat_id, None)
    _pending_action_generic.pop(chat_id, None)

    if outcome_payload.get("suppress_telegram"):
        log.info("suppress_telegram_outcome", reason=_SUPPRESS_TELEGRAM_REASON)
        return

    reason = outcome_payload.get("reason", "unknown")
    action_type = outcome_payload.get("action_type", "")
    action_target = outcome_payload.get("action_target", "")

    reason_text = {
        "owner_rejected": "cancelled",
        "timed_out": "timed out — no response received",
        "not_found": "the document was not found",
    }.get(reason, reason)

    if action_type == _ACTION_DOCUMENT_DELETE:
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
    """Receive deletion.complete or deletion.not_found from Block 13 and notify owner.

    suppress_telegram: if True in the payload, skips the Telegram send.
    """
    if result_payload.get("suppress_telegram"):
        log.info("suppress_telegram_deletion_result", reason=_SUPPRESS_TELEGRAM_REASON)
        return

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

    telegram_commands_total.labels(command="feedback").inc()

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


# ---------------------------------------------------------------------------
# v0.7 — Generic action confirmation commands (web.search, reminder.schedule)
# ---------------------------------------------------------------------------

async def handle_confirm_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/confirm_action — owner confirms a pending generic action (v0.7).

    Emits action.owner_response with confirmed=True to Block 13 → Block 9.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="other").inc()

    # v0.8 — tool management: check pending tool ops before generic actions
    if chat_id in _pending_tool_ops:
        op_data = _pending_tool_ops.pop(chat_id)
        tool_name = op_data["tool_name"]
        op = op_data["op"]
        event_type = "admin.tool_disable" if op == "disable" else "admin.tool_enable"

        # Retain state until admin.tool_updated push arrives (success message comes then)
        _confirmed_tool_ops[chat_id] = op_data

        conversation_id = sessions.get_or_create(chat_id)
        await _emit_to_orchestrator(
            event_type,
            {
                "event_id": str(uuid.uuid4()),
                "conversation_id": str(conversation_id),
                "payload": {
                    "tool_name": tool_name,
                    "confirmed": True,
                    "chat_id": chat_id,
                },
            },
        )
        log.info("tool_op_confirmed", chat_id=chat_id, tool_name=tool_name, op=op)
        return  # Success message delivered via admin.tool_updated HTTP push

    action_request_id = _pending_action_generic.get(chat_id)
    if not action_request_id:
        await update.message.reply_text(
            "No pending action to confirm."
        )
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        _EVENT_OWNER_RESPONSE,
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

    _pending_action_generic.pop(chat_id, None)

    log.info("generic_action_confirmed_by_owner", chat_id=chat_id, action_request_id=action_request_id)
    await update.message.reply_text("Confirmed.")


async def handle_cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel_action — owner cancels a pending generic action (v0.7).

    Emits action.owner_response with confirmed=False to Block 13 → Block 9.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="other").inc()

    # v0.8 — tool management: check pending tool ops before generic actions
    if chat_id in _pending_tool_ops:
        op_data = _pending_tool_ops.pop(chat_id)
        tool_name = op_data["tool_name"]
        op = op_data["op"]
        # Cancel message per Block 3 UX spec (section 2.5 / 3.5)
        if op == "disable":
            cancel_text = f"Cancelled. {tool_name} remains enabled."
        else:
            cancel_text = f"Cancelled. {tool_name} remains disabled."
        await update.message.reply_text(cancel_text)
        log.info("tool_op_cancelled", chat_id=chat_id, tool_name=tool_name, op=op)
        return

    action_request_id = _pending_action_generic.pop(chat_id, None)
    if not action_request_id:
        await update.message.reply_text("No pending action to cancel.")
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    await _emit_to_orchestrator(
        _EVENT_OWNER_RESPONSE,
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

    log.info("generic_action_cancelled_by_owner", chat_id=chat_id, action_request_id=action_request_id)
    await update.message.reply_text("Cancelled.")


# ---------------------------------------------------------------------------
# v0.4 — Mobile ingest (D-114) and /list, /status commands
# ---------------------------------------------------------------------------

# Pending mobile ingest state: chat_id → {file_id, original_filename, file_size, mime_type}
# Set when a document is received without /ingest caption.
# Cleared on /ingest_confirm or overwritten by a new document.
_pending_ingests: dict[int, dict[str, Any]] = {}

# Block 20 — in-memory rate limit state (D-125, v0.6).
# Tracks query count in the current UTC clock hour.
# Resets when the clock hour changes.
_rate_limit_state: dict[str, Any] = {"hour": None, "count": 0}


async def handle_document_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a document sent without /ingest caption — mobile-compatible ingest (D-114).

    Stores pending ingest state and prompts owner for confirmation.
    The owner sends /ingest_confirm to complete the ingest.
    Desktop caption flow (/ingest caption) is handled separately and
    unchanged — this handler only fires when there is no /ingest caption.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="ingest").inc()

    document = update.message.document
    if not document:
        return

    original_name = document.file_name or "document"

    # D-098: size check before accepting
    if document.file_size and document.file_size > MAX_INGEST_BYTES:
        await update.message.reply_text(
            f"File too large ({document.file_size // (1024 * 1024)} MB). Maximum is 10 MB."
        )
        return

    # Store pending state (overwrites if owner sends another file before confirming)
    _pending_ingests[chat_id] = {
        "file_id": document.file_id,
        "original_filename": original_name,
        "file_size": document.file_size,
        "mime_type": document.mime_type or "application/octet-stream",
    }

    log.info(
        "mobile_ingest_pending",
        chat_id=chat_id,
        original_filename=original_name,
    )

    await update.message.reply_text(
        f"Ingest {original_name}?\n"
        "Send /ingest_confirm to proceed, or ignore to cancel."
    )


async def handle_ingest_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ingest_confirm — complete a pending mobile ingest (D-114).

    Downloads the file stored in pending state, uploads to MinIO,
    and emits ingest.received exactly as the desktop caption flow does.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="ingest").inc()

    log.info("ingest_confirm_command_received", chat_id=chat_id)

    pending = _pending_ingests.pop(chat_id, None)
    if not pending:
        log.warning("ingest_confirm_no_pending_state", chat_id=chat_id)
        await update.message.reply_text(
            "No pending ingest. Send a file first, then /ingest_confirm."
        )
        return

    original_name = pending["original_filename"]
    file_id = pending["file_id"]
    file_size = pending["file_size"]
    mime_type = pending["mime_type"]

    # Download from Telegram
    try:
        tg_file = await context.bot.get_file(file_id)
        raw_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:
        log.error("ingest_confirm_download_failed", chat_id=chat_id, error=str(exc))
        await update.message.reply_text(
            "Could not download the file. Please send it again and retry."
        )
        return

    source_key = f"{uuid.uuid4()}/{original_name}"

    try:
        await upload_document(source_key, raw_bytes, mime_type)
    except RuntimeError as exc:
        log.error("minio_upload_failed", source_key=source_key, error=str(exc))
        await update.message.reply_text(
            "Could not store the file. Please try again."
        )
        return

    conversation_id = sessions.get_or_create(chat_id)
    event_id = uuid.uuid4()

    log.info(
        "ingest_confirm_received",
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
                "file_size": file_size,
                "content_type": mime_type,
                "chat_id": chat_id,
            },
        },
    )

    await update.message.reply_text(
        f"Received {original_name}. Processing — I will follow up when done."
    )


async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
    """Handle /list — show all ingested documents (v0.4).

    Calls the orchestrator's /retrieve/document-list endpoint (D-043 pattern).
    Returns filename, chunk count, and ingest date for each document,
    newest first. Replies with a clear message if the knowledge base is empty.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="list").inc()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/retrieve/document-list",
                json={"zone_scope": "personal"},
                timeout=10.0,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        log.error("list_fetch_failed", chat_id=chat_id, error=str(exc))
        await update.message.reply_text("Could not retrieve document list. Please try again.")
        return

    documents = result.get("documents", [])
    if not documents:
        await update.message.reply_text(
            "No documents ingested yet.\n"
            "Send a file with /ingest as the caption (desktop) or just send "
            "a file and reply /ingest_confirm (mobile)."
        )
        return

    total = result.get("total", len(documents))
    lines = [f"Knowledge base — {total} document(s):\n"]
    for i, doc in enumerate(documents, 1):
        date = doc["ingested_at"][:10]  # YYYY-MM-DD
        chunks = doc["chunk_count"]
        lines.append(f"{i}. {doc['filename']} — {chunks} chunk(s) — {date}")

    await update.message.reply_text("\n".join(lines))
    log.info("list_delivered", chat_id=chat_id, doc_count=total)


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
    """Handle /status — show system status summary (v0.4).

    Calls the orchestrator's /retrieve/status endpoint (D-043 pattern).
    Returns document count, chunk count, last ingest, and last query time.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="status").inc()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/retrieve/status",
                json={"zone_scope": "personal"},
                timeout=10.0,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        log.error("status_fetch_failed", chat_id=chat_id, error=str(exc))
        await update.message.reply_text("Could not retrieve status. Please try again.")
        return

    doc_count = result.get("doc_count", 0)
    chunk_count = result.get("chunk_count", 0)
    last_doc_name = result.get("last_doc_name")
    last_doc_at = result.get("last_doc_at")
    last_query_at = result.get("last_query_at")
    # Block 20 — spend data (D-125, v0.6)
    llm_spend_today_usd = result.get("llm_spend_today_usd", 0.0)
    daily_cap_usd = result.get("daily_cap_usd")  # None if not configured

    lines = ["CLIVE Status\n"]

    if doc_count == 0:
        lines.append("Knowledge base: empty")
    else:
        lines.append(f"Knowledge base: {doc_count} document(s), {chunk_count:,} chunk(s)")

    if last_doc_name and last_doc_at:
        lines.append(f"Last ingest: {last_doc_name} ({last_doc_at[:10]})")

    if last_query_at:
        lines.append(f"Last query: {last_query_at[:10]}")
    else:
        lines.append("Last query: none yet")


    # Block 20 — LLM spend display (D-125, v0.6)
    lines.append(f"LLM spend today: ${llm_spend_today_usd:.4f}")
    if daily_cap_usd is not None:
        lines.append(f"Daily cap: ${daily_cap_usd:.4f}")
    else:
        lines.append("Daily cap: no cap set")
    lines.append("\n/list — see all documents")

    await update.message.reply_text("\n".join(lines))
    log.info("status_delivered", chat_id=chat_id, doc_count=doc_count, llm_spend=llm_spend_today_usd)


# ---------------------------------------------------------------------------
# v0.8 — Tool management helpers (Block 3 UX spec, D-137)
# ---------------------------------------------------------------------------

def _format_tool_entry(row: Any) -> str:
    """Format a single tool_registry row per Block 3 UX design specification."""
    tool_name = row["tool_name"]
    display_name = row["display_name"]
    version = row["version"]
    description = row["description"]
    enabled = row["enabled"]
    deprecated = row["deprecated"]
    deprecation_note = row["deprecation_note"]
    health_status = row["health_status"]

    status = "enabled" if enabled else "disabled"
    if deprecated:
        status += " [deprecated]"
    if health_status and health_status != "healthy":
        status += f" [health: {health_status}]"

    lines = [
        f"`{tool_name}` v{version} — {status}",
        f"{display_name}. {description}",
    ]
    if deprecated and deprecation_note:
        lines.append(f"Deprecated: {deprecation_note}")

    return "\n".join(lines)


def _pack_tool_messages(header: str, entries: list[str]) -> list[str]:
    """Split tool entries into messages ≤ 3800 chars (UX spec section 1.5).

    The first message carries the header; continuation messages use
    the reduced header "Tools (continued)" per UX spec.
    """
    LIMIT = 3800

    def build_msg(h: str, es: list[str]) -> str:
        return h + "\n\n" + "\n\n".join(es)

    messages: list[str] = []
    current_header = header
    current_entries: list[str] = []

    for entry in entries:
        candidate = build_msg(current_header, current_entries + [entry])
        if len(candidate) > LIMIT and current_entries:
            messages.append(build_msg(current_header, current_entries))
            current_header = "Tools (continued)"
            current_entries = [entry]
        else:
            current_entries.append(entry)

    if current_entries:
        messages.append(build_msg(current_header, current_entries))

    return messages


# ---------------------------------------------------------------------------
# v0.8 — Tool management command handlers (D-137, D-006)
# ---------------------------------------------------------------------------

_TOOL_REGISTRY_UNAVAILABLE = "Tool registry is unavailable. Try again shortly."


async def _reply_tool_already_enabled(message, tool_name: str, deprecated: bool, deprecation_note: str | None) -> None:
    if deprecated:
        note = deprecation_note or ""
        note_suffix = f" {note}" if note else ""
        await message.reply_text(
            f"{tool_name} is already enabled.\n"
            f"Note: this tool is deprecated.{note_suffix}"
        )
    else:
        await message.reply_text(f"{tool_name} is already enabled.")

async def handle_tools(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
    """/tools — list all registered tools (v0.8, D-137).

    Direct DB read (admin operation — same pattern as handle_activate).
    Formatted per Block 3 UX design specification.
    Paginates at 3800 chars per UX spec section 1.5.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="tools").inc()

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tool_name, display_name, version, description,
                       enabled, deprecated, deprecation_note, health_status
                FROM clive_state.tool_registry
                ORDER BY tool_name
                """
            )
    except Exception as exc:
        log.error("tool_registry_fetch_failed", chat_id=chat_id, error=str(exc))
        await update.message.reply_text(_TOOL_REGISTRY_UNAVAILABLE)
        return

    if not rows:
        await update.message.reply_text("No tools are registered.")
        return

    entries = [_format_tool_entry(row) for row in rows]
    header = f"Tools — {len(rows)} registered"
    messages = _pack_tool_messages(header, entries)

    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")

    log.info("tools_listed", chat_id=chat_id, tool_count=len(rows))


async def handle_tool_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tool_disable <name> — disable a registered tool (v0.8, D-137, D-006).

    Direct DB read for pre-checks.
    State change routes through Block 9 confirmation gate (D-006):
      owner confirms with /confirm_action → admin.tool_disable emitted to Block 13.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="tools").inc()

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /tool_disable <tool_name>\n"
            "Use /tools to see registered tool names."
        )
        return

    tool_name = args[0].strip()

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tool_name, display_name, version, description,
                       enabled, deprecated, deprecation_note
                FROM clive_state.tool_registry
                WHERE tool_name = $1
                """,
                tool_name,
            )
    except Exception as exc:
        log.error(
            "tool_registry_fetch_failed",
            chat_id=chat_id,
            tool_name=tool_name,
            error=str(exc),
        )
        await update.message.reply_text(_TOOL_REGISTRY_UNAVAILABLE)
        return

    if row is None:
        await update.message.reply_text(
            f"No tool named {tool_name} is registered.\n"
            "Use /tools to see registered tool names."
        )
        return

    if not row["enabled"]:
        await update.message.reply_text(f"{tool_name} is already disabled.")
        return

    # Tool exists and is enabled — require explicit confirmation (D-006)
    display_name = row["display_name"]
    version = row["version"]
    description = row["description"]

    _pending_tool_ops[chat_id] = {
        "op": "disable",
        "tool_name": tool_name,
        "deprecated": bool(row["deprecated"]),
    }

    # Exact confirmation prompt per Block 3 UX spec section 2.5
    prompt = (
        f"Disable {tool_name}?\n\n"
        f"{display_name} · v{version}\n"
        f"{description}\n\n"
        "When disabled, this tool will be unavailable until re-enabled.\n\n"
        "/confirm_action — confirm disable\n"
        "/cancel_action — cancel"
    )
    await update.message.reply_text(prompt)

    log.info("tool_disable_confirmation_sent", chat_id=chat_id, tool_name=tool_name)


async def handle_tool_enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tool_enable <name> — enable a registered tool (v0.8, D-137, D-006).

    Mirrors handle_tool_disable.
    Deprecated-tool variant includes deprecation note in the confirmation prompt
    per Block 3 UX spec section 3.6.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="tools").inc()

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /tool_enable <tool_name>\n"
            "Use /tools to see registered tool names."
        )
        return

    tool_name = args[0].strip()

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tool_name, display_name, version, description,
                       enabled, deprecated, deprecation_note
                FROM clive_state.tool_registry
                WHERE tool_name = $1
                """,
                tool_name,
            )
    except Exception as exc:
        log.error(
            "tool_registry_fetch_failed",
            chat_id=chat_id,
            tool_name=tool_name,
            error=str(exc),
        )
        await update.message.reply_text(_TOOL_REGISTRY_UNAVAILABLE)
        return

    if row is None:
        await update.message.reply_text(
            f"No tool named {tool_name} is registered.\n"
            "Use /tools to see registered tool names."
        )
        return

    if row["enabled"]:
        await _reply_tool_already_enabled(
            update.message, tool_name, bool(row["deprecated"]), row["deprecation_note"]
        )
        return

    # Tool exists and is disabled — require explicit confirmation (D-006)
    display_name = row["display_name"]
    version = row["version"]
    description = row["description"]
    deprecated = bool(row["deprecated"])
    deprecation_note = row["deprecation_note"] or ""

    _pending_tool_ops[chat_id] = {
        "op": "enable",
        "tool_name": tool_name,
        "deprecated": deprecated,
    }

    if deprecated:
        # UX spec section 3.6 — deprecated tool confirmation variant
        prompt = (
            f"Enable {tool_name}?\n\n"
            f"{display_name} · v{version} [deprecated]\n"
            f"{description}\n\n"
            f"Deprecated: {deprecation_note}\n\n"
            "/confirm_action — enable anyway\n"
            "/cancel_action — cancel"
        )
    else:
        # UX spec section 3.5 — standard enable confirmation
        prompt = (
            f"Enable {tool_name}?\n\n"
            f"{display_name} · v{version}\n"
            f"{description}\n\n"
            "This tool will be available immediately.\n\n"
            "/confirm_action — confirm enable\n"
            "/cancel_action — cancel"
        )

    await update.message.reply_text(prompt)

    log.info(
        "tool_enable_confirmation_sent",
        chat_id=chat_id,
        tool_name=tool_name,
        deprecated=deprecated,
    )


# ---------------------------------------------------------------------------
# v0.8 — Tool updated/error delivery (push from Block 13)
# ---------------------------------------------------------------------------

async def deliver_tool_updated(payload: dict[str, Any], chat_id: int) -> None:
    """Receive admin.tool_updated from Block 13 and notify owner (v0.8).

    Resolves success message text from _confirmed_tool_ops local state,
    with fallback to payload fields for resilience.
    Success text per Block 3 UX spec sections 2.6 / 3.7.
    """
    op_data = _confirmed_tool_ops.pop(chat_id, None)

    if op_data:
        tool_name = op_data["tool_name"]
        op = op_data["op"]
        deprecated = op_data.get("deprecated", False)
    else:
        # Fallback if local state was lost (e.g. process restart)
        tool_name = payload.get("tool_name", "unknown")
        op = payload.get("operation", "")
        deprecated = payload.get("deprecated", False)

    if op == "disable":
        text = f"{tool_name} disabled."
    elif op == "enable":
        if deprecated:
            text = f"{tool_name} enabled. Note: this tool is deprecated."
        else:
            text = f"{tool_name} enabled."
    else:
        text = f"{tool_name} updated."

    if _app:
        await _app.bot.send_message(chat_id=chat_id, text=text)
        log.info("tool_updated_delivered", chat_id=chat_id, tool_name=tool_name, op=op)


async def deliver_tool_error(payload: dict[str, Any], chat_id: int) -> None:  # noqa: ARG001  # NOSONAR
    """Receive admin.tool_error from Block 13 and notify owner (v0.8)."""
    _confirmed_tool_ops.pop(chat_id, None)

    if _app:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=_TOOL_REGISTRY_UNAVAILABLE,
        )
        log.warning("tool_error_delivered", chat_id=chat_id)


# ---------------------------------------------------------------------------
# v0.10 — /whoami command (D-144)
# ---------------------------------------------------------------------------

async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
    """Return the caller's user profile from clive_state.users.

    D-144: /whoami returns telegram_chat_id, role, zone_access.
    D-001: gated by is_authenticated — owner-only at v0.1.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="other").inc()

    profile = await auth.get_user_profile(chat_id)

    if profile is None:
        text = (
            "You are authenticated but not yet registered in the users table.\n"
            "This resolves on next service restart."
        )
    else:
        zones = ", ".join(profile["zone_access"]) or "none"
        text = (
            f"*User Profile*\n"
            f"Chat ID: `{profile['telegram_chat_id']}`\n"
            f"Role: `{profile['role']}`\n"
            f"Zone access: `{zones}`\n"
            f"Member since: {profile['created_at'][:10]}"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# D-119 — /help command
# ---------------------------------------------------------------------------

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
    """/help — list all available commands (D-119)."""
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    if not is_authenticated(chat_id):
        return

    telegram_commands_total.labels(command="other").inc()

    text = (
        "Commands\n\n"
        "/start — reset conversation\n"
        "/list — list ingested documents\n"
        "/status — system status\n"
        "/whoami — show your user profile and zone access\n\n"
        "/ingest — ingest file (send file with /ingest as caption)\n"
        "/ingest_confirm — confirm pending ingest (mobile)\n"
        "/delete <filename> — delete a document\n\n"
        "/tools — list all registered tools\n"
        "/tool_disable <tool_name> — disable a tool (requires confirmation)\n"
        "/tool_enable <tool_name> — enable a tool (requires confirmation)\n\n"
        "/bad — tag last response as poor quality\n"
        "/activate <document_type> — activate a pending system document\n"
        "/help — this list"
    )

    await update.message.reply_text(text)
