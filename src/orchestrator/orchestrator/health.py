"""HTTP health endpoint and API routes for Block 13."""

from __future__ import annotations

from aiohttp import web

from .bus import bus
from .events.schema import CLIVEEvent
from .retrieval import retrieve, retrieve_system_document


async def handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.json_response({"status": "ok", "block": 13})


async def handle_event_intake(request: web.Request) -> web.Response:
    """Accept inbound events from Block 8 and Block 23, route through bus."""
    data = await request.json()
    event = CLIVEEvent(**data)
    await bus.publish(event)
    return web.json_response({"status": "accepted"})


async def handle_retrieve_knowledge(request: web.Request) -> web.Response:
    """Broker retrieval call to Block 16 (D-043)."""
    data = await request.json()
    result = await retrieve(
        retrieval_query=data["retrieval_query"],
        zone_scope=data["zone_scope"],
        result_limit=data.get("result_limit", 20),
        conversation_id=data.get("conversation_id"),
    )
    return web.json_response(result)


async def handle_retrieve_system_document(request: web.Request) -> web.Response:
    """Broker system document retrieval (D-048)."""
    data = await request.json()
    result = await retrieve_system_document(
        document_type=data["document_type"],
        zone_scope=data["zone_scope"],
        version_id=data.get("version_id"),
    )
    return web.json_response(result)


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/events", handle_event_intake)
    app.router.add_post("/retrieve/knowledge", handle_retrieve_knowledge)
    app.router.add_post("/retrieve/system-document", handle_retrieve_system_document)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
