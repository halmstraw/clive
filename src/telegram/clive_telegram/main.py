"""Block 23 Telegram surface entry point.

Starts the Telegram bot (polling) and an HTTP server that receives
push responses from Block 13.

v0.3 additions:
  /delete, /confirm_delete, /cancel_delete — T8 deletion (D-109, D-006)
  /bad — Block 18 feedback (D-100)
  /action-confirmation HTTP endpoint — Block 9 push to surface
  /action-outcome HTTP endpoint — Block 9 rejection/timeout push
  /deletion-result HTTP endpoint — deletion.complete / deletion.not_found push

v0.4 additions:
  /ingest_confirm — complete a pending mobile ingest (D-114)
  /list — list ingested documents (v0.4)
  /status — system status summary (v0.4)
  Document handler without /ingest caption — mobile ingest prompt (D-114)

v0.5 additions:
  /metrics — Prometheus scrape endpoint (D-122 Phase 2)
"""

from __future__ import annotations

import asyncio
import os
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .auth import get_owner_chat_id
from .bot import (
    deliver_action_confirmation,
    deliver_action_outcome,
    deliver_alert,
    deliver_deletion_result,
    deliver_ingest_status,
    deliver_response,
    handle_activate,
    handle_bad,
    handle_cancel_delete,
    handle_confirm_activate,
    handle_confirm_delete,
    handle_delete,
    handle_document_received,
    handle_ingest,
    handle_ingest_confirm,
    handle_list,
    handle_message,
    handle_start,
    handle_status,
    set_app,
)
from . import db

load_dotenv("/etc/clive/secrets.env")

log = structlog.get_logger()


async def handle_response_push(request: web.Request) -> web.Response:
    """Receive query.response events pushed from Block 13."""
    data = await request.json()
    chat_id = get_owner_chat_id()
    asyncio.create_task(deliver_response(data, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_alert_push(request: web.Request) -> web.Response:
    """Receive alert.triggered events pushed from Block 13."""
    data = await request.json()
    chat_id = get_owner_chat_id()
    asyncio.create_task(deliver_alert(data, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_ingest_status_push(request: web.Request) -> web.Response:
    """Receive ingest.processed or ingest.rejected events pushed from Block 13."""
    data = await request.json()
    chat_id = get_owner_chat_id()
    payload = {**data, **data.get("payload", {})}
    asyncio.create_task(deliver_ingest_status(payload, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_action_confirmation_push(request: web.Request) -> web.Response:
    """Receive action.confirmation_requested from Block 13 (Block 9 → surface).

    Block 9 has stored the pending action and now asks Block 23 to prompt
    the owner for confirmation. Block 23 stores the action_request_id and
    sends the confirmation prompt.
    """
    data = await request.json()
    chat_id_raw = data.get("chat_id") or data.get("payload", {}).get("chat_id")
    if chat_id_raw is None:
        chat_id_raw = get_owner_chat_id()
    chat_id = int(chat_id_raw)
    payload = {**data, **data.get("payload", {})}
    asyncio.create_task(deliver_action_confirmation(payload, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_action_outcome_push(request: web.Request) -> web.Response:
    """Receive action.rejected from Block 13 (Block 9 rejection/timeout → surface)."""
    data = await request.json()
    chat_id_raw = data.get("chat_id") or data.get("payload", {}).get("chat_id")
    if chat_id_raw is None:
        chat_id_raw = get_owner_chat_id()
    chat_id = int(chat_id_raw)
    payload = {**data, **data.get("payload", {})}
    asyncio.create_task(deliver_action_outcome(payload, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_deletion_result_push(request: web.Request) -> web.Response:
    """Receive deletion.complete or deletion.not_found from Block 13."""
    data = await request.json()
    chat_id_raw = data.get("chat_id") or data.get("payload", {}).get("chat_id")
    if chat_id_raw is None:
        chat_id_raw = get_owner_chat_id()
    chat_id = int(chat_id_raw)
    payload = {**data, **data.get("payload", {})}
    asyncio.create_task(deliver_deletion_result(payload, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 23})


async def handle_metrics(request: web.Request) -> web.Response:  # noqa: ARG001
    """Expose Prometheus metrics for scraping (D-122 Phase 2)."""
    data = generate_latest()
    return web.Response(body=data, content_type=CONTENT_TYPE_LATEST)


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    log.info("telegram_surface_starting", block=23)

    # Initialise DB pool for D-079 system document activation and Block 18 feedback
    await db.init_pool()

    # Build Telegram application
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("activate", handle_activate))
    application.add_handler(CommandHandler("confirm_activate", handle_confirm_activate))

    # v0.3 — T8 deletion commands (D-109, D-006)
    application.add_handler(CommandHandler("delete", handle_delete))
    application.add_handler(CommandHandler("confirm_delete", handle_confirm_delete))
    application.add_handler(CommandHandler("cancel_delete", handle_cancel_delete))

    # v0.3 — Block 18 feedback command
    application.add_handler(CommandHandler("bad", handle_bad))

    # v0.4 — mobile ingest and new commands (D-114)
    application.add_handler(CommandHandler("ingest_confirm", handle_ingest_confirm))
    application.add_handler(CommandHandler("list", handle_list))
    application.add_handler(CommandHandler("status", handle_status))

    # Document handlers — order matters:
    # 1. /ingest caption (desktop, D-101) takes priority
    # 2. Any other document (mobile prompt, D-114)
    application.add_handler(
        MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/ingest"), handle_ingest)
    )
    application.add_handler(
        MessageHandler(
            filters.Document.ALL & ~filters.CaptionRegex(r"^/ingest"),
            handle_document_received,
        )
    )

    # Free-text queries
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    set_app(application)

    # Build HTTP server for Block 13 push delivery
    http_app = web.Application()
    http_app.router.add_post("/response", handle_response_push)
    http_app.router.add_post("/alert", handle_alert_push)
    http_app.router.add_post("/ingest-status", handle_ingest_status_push)

    # v0.3 — Block 9 and deletion result endpoints
    http_app.router.add_post("/action-confirmation", handle_action_confirmation_push)
    http_app.router.add_post("/action-outcome", handle_action_outcome_push)
    http_app.router.add_post("/deletion-result", handle_deletion_result_push)

    http_app.router.add_get("/health", handle_health)
    http_app.router.add_get("/metrics", handle_metrics)

    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8082)
    await site.start()

    log.info("http_server_started", port=8082)

    # Start Telegram polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)

    log.info("telegram_polling_started")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    await runner.cleanup()
    log.info("telegram_surface_stopped")


if __name__ == "__main__":
    asyncio.run(main())
