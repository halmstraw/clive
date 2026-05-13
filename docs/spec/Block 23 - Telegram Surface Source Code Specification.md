*Block 23 implementation specification — produced May 2026. All design decisions resolved. Ready for implementation.*

---
# Block 23 — Telegram Surface Source Code Specification (Claude Code Input)

## Purpose

Complete implementation specification for the Block 23 Telegram surface. This is the owner-facing layer — the only thing standing between a working CLIVE and the owner's phone.

**Decisions implemented:** D-035, D-050, D-057, D-058, D-061, D-003, D-025, D-028

**Claude Code instruction:** Create all files under `src/telegram/`. Commit as `feat: Block 23 Telegram surface scaffold`.

---

## Repository Structure to Create

```
src/
  telegram/
    Dockerfile
    pyproject.toml
    telegram/
      __init__.py
      main.py        # Entry point — starts Telegram bot
      bot.py         # Message handler — emits query.received, renders query.response
      session.py     # conversation_id management (D-018 — stateless, ID in payload)
      auth.py        # Channel-as-authentication (D-057, D-058)
```

---

## src/telegram/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY telegram/ ./telegram/

RUN useradd -m -u 1000 clive
USER clive

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import telegram; print('ok')" || exit 1

CMD ["python", "-m", "telegram.main"]
```

---

## src/telegram/pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "clive-telegram"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "python-telegram-bot>=21.0",  # Async Telegram bot library
    "httpx>=0.27",                 # HTTP client for Block 13 event submission
    "structlog>=24.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## src/telegram/telegram/auth.py

```python
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
```

---

## src/telegram/telegram/session.py

```python
"""Conversation session identity management.

D-018: Block 23 is stateless — conversation_id is carried in event
payloads, not held in Block 23 local state.

Telegram threads map naturally to conversation_ids:
- A new private message from the owner starts or continues a session.
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
```

---

## src/telegram/telegram/bot.py

```python
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
        response_text += "\n\n_(Answered from general knowledge — no relevant documents found)_"

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

    severity_prefix = {"info": "[INFO]", "warn": "[WARN]", "error": "[ERROR]"}.get(severity, "[INFO]")
    text = f"{severity_prefix} *{title}*\n{body}"

    if _app:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
```

---

## src/telegram/telegram/main.py

```python
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
from .bot import deliver_alert, deliver_response, handle_message, handle_start, set_app

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


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 23})


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    log.info("telegram_surface_starting", block=23)

    # Build Telegram application
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    set_app(application)

    # Build HTTP server for Block 13 push delivery
    http_app = web.Application()
    http_app.router.add_post("/response", handle_response_push)
    http_app.router.add_post("/alert", handle_alert_push)
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
```

---

## Compose addition — docker-compose.yml

Add the `telegram` service to `infrastructure/compose/docker-compose.yml`:

```yaml
telegram:
  image: ghcr.io/clive-owner/clive-telegram:${TELEGRAM_IMAGE_TAG:-latest}
  container_name: clive-telegram
  restart: always
  env_file: /etc/clive/secrets.env
  environment:
    - CLIVE_ENV=production
    - ORCHESTRATOR_URL=http://orchestrator:8080
  depends_on:
    orchestrator:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 15s
  networks:
    - clive-internal
```

Add `TELEGRAM_IMAGE_TAG=latest` and `TELEGRAM_OWNER_CHAT_ID=` to `.env.example`.

---

## Block 13 additions needed — push routing

Block 13 needs to push `query.response` and `alert.triggered` events to Block 23. Add to `src/orchestrator/orchestrator/bus.py` or a new `push.py`:

```python
import os
import httpx

TELEGRAM_URL = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram:8082")

async def push_response_to_surface(event: CLIVEEvent) -> None:
    """Push query.response to Block 23 (Telegram surface)."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/response",
            json=event.payload,
            timeout=10.0,
        )

async def push_alert_to_surface(event: CLIVEEvent) -> None:
    """Push alert.triggered to Block 23."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_URL}/alert",
            json=event.payload,
            timeout=10.0,
        )
```

Register as subscribers in Block 13 startup:

```python
from .push import push_response_to_surface, push_alert_to_surface
from .events.taxonomy import QUERY_RESPONSE, ALERT_TRIGGERED

bus.subscribe(QUERY_RESPONSE, block_id=23, handler=push_response_to_surface)
bus.subscribe(ALERT_TRIGGERED, block_id=23, handler=push_alert_to_surface)
```

Also add `TELEGRAM_SERVICE_URL=http://telegram:8082` to `infrastructure/compose/.env.example` and to the orchestrator's environment in `docker-compose.yml`.

---

## Required environment variables summary

All secrets go in `/etc/clive/secrets.env` (Ansible-injected). Add to the `clive-secrets` Ansible role:

| Variable | Block | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 23 | BotFather token |
| `TELEGRAM_OWNER_CHAT_ID` | 23 | Owner's Telegram chat ID (get via @userinfobot) |
| `ANTHROPIC_API_KEY` | 8 | Anthropic API key for LiteLLM |
| `AUDIT_WRITER_PASSWORD` | 13 | Password for `clive_audit_writer` PostgreSQL role |
| `APP_DB_PASSWORD` | 13 | Password for `clive_app` PostgreSQL role |
| `POSTGRES_PASSWORD` | 16 | PostgreSQL superuser password |
| `MINIO_ROOT_USER` | 16 | MinIO root user |
| `MINIO_ROOT_PASSWORD` | 16 | MinIO root password |

---

## Pre-launch checklist

Before first `terraform apply` and first message to CLIVE:

- [ ] Terraform state bucket bootstrapped (see `docs/runbooks/terraform-bootstrap.md`)
- [ ] All GitHub Actions secrets populated
- [ ] Telegram bot created via BotFather — token saved as `TELEGRAM_BOT_TOKEN`
- [ ] Owner chat ID obtained via @userinfobot — saved as `TELEGRAM_OWNER_CHAT_ID`
- [ ] Anthropic API key obtained — saved as `ANTHROPIC_API_KEY`
- [ ] PostgreSQL role passwords chosen and saved
- [ ] MinIO credentials chosen and saved
- [ ] Personality document loaded into Block 16 and activated (D-049)
- [ ] Alignment rules document loaded into Block 16 and activated (D-049)
- [ ] At least one knowledge document ingested into Block 16

---

*Block 23 source code specification — Architect*
*May 2026. Claude Code: commit as `feat: Block 23 Telegram surface scaffold`.*
*After all three scaffolds are committed and infrastructure is up, CLIVE is ready for first message.*
