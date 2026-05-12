"""Block 23 Telegram surface entry point.

Starts the Telegram bot (polling) and an HTTP server that receives
push responses from Block 13.
"""

from __future__ import annotations

import asyncio
import os
import signal

import structlog
from aiohttp import web
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .auth import get_owner_chat_id
from .bot import (
    deliver_alert,
    deliver_ingest_status,
    deliver_response,
    handle_activate,
    handle_confirm_activate,
    handle_ingest,
    handle_message,
    handle_start,
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
    # Merge payload fields into the top-level dict for deliver_ingest_status
    payload = {**data, **data.get("payload", {})}
    asyncio.create_task(deliver_ingest_status(payload, chat_id))
    return web.json_response({"status": "accepted"})


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 23})


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    log.info("telegram_surface_starting", block=23)

    # Initialise DB pool for D-079 system document activation
    await db.init_pool()

    # Build Telegram application
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("activate", handle_activate))
    application.add_handler(CommandHandler("confirm_activate", handle_confirm_activate))
    # D-101: caption command — document with /ingest caption
    application.add_handler(
        MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/ingest"), handle_ingest)
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    set_app(application)

    # Build HTTP server for Block 13 push delivery
    http_app = web.Application()
    http_app.router.add_post("/response", handle_response_push)
    http_app.router.add_post("/alert", handle_alert_push)
    http_app.router.add_post("/ingest-status", handle_ingest_status_push)
    http_app.router.add_get("/health", handle_health)

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
