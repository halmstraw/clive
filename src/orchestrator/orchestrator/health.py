"""HTTP health endpoint and API routes for Block 13.

v0.3: added /retrieve/document-by-filename for T8 deletion lookup (D-109).
"""

from __future__ import annotations

from aiohttp import web

from .bus import bus
from .events.schema import CLIVEEvent
from .retrieval import retrieve, retrieve_document_by_filename, retrieve_system_document


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


async def handle_retrieve_document_by_filename(request: web.Request) -> web.Response:
    """Look up source_keys for a given filename in Block 16 (D-109, T8 deletion).

    Returns {source_keys: [...], chunk_count: N} or 404 if not found.
    Used by Block 23's /delete command to verify the document exists before
    emitting action.pending to Block 9.
    """
    data = await request.json()
    filename = data.get("filename", "")
    zone_scope = data.get("zone_scope", "personal")

    if not filename:
        return web.json_response({"error": "filename required"}, status=400)

    result = await retrieve_document_by_filename(filename=filename, zone_scope=zone_scope)
    if not result["source_keys"]:
        return web.json_response({"error": "not found"}, status=404)

    return web.json_response(result)


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/events", handle_event_intake)
    app.router.add_post("/retrieve/knowledge", handle_retrieve_knowledge)
    app.router.add_post("/retrieve/system-document", handle_retrieve_system_document)
    app.router.add_post("/retrieve/document-by-filename", handle_retrieve_document_by_filename)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
