"""Tests for Block 15 HTTP entry point."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class TestHandleIngest:
    async def test_returns_202_accepted(self):
        from processing.main import handle_ingest

        app = web.Application()
        app.router.add_post("/ingest", handle_ingest)

        async with TestClient(TestServer(app)) as client:
            with patch("processing.main.process", new=AsyncMock()):
                resp = await client.post(
                    "/ingest",
                    json={"source_key": "doc.txt", "content_type": "text/plain"},
                )
                assert resp.status == 202
                body = await resp.json()
                assert body["status"] == "accepted"

    async def test_process_called_with_source_key(self):
        from processing.main import handle_ingest

        app = web.Application()
        app.router.add_post("/ingest", handle_ingest)

        async with TestClient(TestServer(app)) as client:
            with patch("processing.main.process", new=AsyncMock()) as mock_process:
                await client.post(
                    "/ingest",
                    json={"source_key": "report.pdf", "content_type": "application/pdf"},
                )
                # process(payload) is called synchronously to create the task
                mock_process.assert_called_once()
                payload_arg = mock_process.call_args[0][0]
                assert payload_arg["source_key"] == "report.pdf"

    async def test_top_level_fields_merged_into_payload(self):
        """Top-level source_key/content_type propagate into payload dict."""
        from processing.main import handle_ingest

        app = web.Application()
        app.router.add_post("/ingest", handle_ingest)

        async with TestClient(TestServer(app)) as client:
            with patch("processing.main.process", new=AsyncMock()) as mock_process:
                # Block 13 may send fields at the top level (not nested under "payload")
                await client.post(
                    "/ingest",
                    json={
                        "event_type": "ingest.received",
                        "source_key": "notes.txt",
                        "content_type": "text/plain",
                        "payload": {},
                    },
                )
                payload_arg = mock_process.call_args[0][0]
                assert payload_arg["source_key"] == "notes.txt"
                assert payload_arg["content_type"] == "text/plain"

    async def test_nested_payload_takes_precedence(self):
        """If source_key is in the nested payload, top-level value is ignored."""
        from processing.main import handle_ingest

        app = web.Application()
        app.router.add_post("/ingest", handle_ingest)

        async with TestClient(TestServer(app)) as client:
            with patch("processing.main.process", new=AsyncMock()) as mock_process:
                await client.post(
                    "/ingest",
                    json={
                        "source_key": "top_level.txt",
                        "payload": {"source_key": "nested.txt"},
                    },
                )
                payload_arg = mock_process.call_args[0][0]
                # nested value wins because the merge only copies if key not in payload
                assert payload_arg["source_key"] == "nested.txt"

    async def test_health_endpoint(self):
        from processing.main import handle_health

        app = web.Application()
        app.router.add_get("/health", handle_health)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            body = await resp.json()
            assert body["block"] == 15
