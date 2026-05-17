"""Extended pipeline and deletion tests — covering remaining missing lines."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_http_mock():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# pipeline.py — uncovered rejection paths
# ---------------------------------------------------------------------------

class TestPipelineRejectionPaths:
    @pytest.mark.asyncio
    async def test_no_chunks_produced_emits_rejected(self):
        from processing import pipeline

        raw = b"."  # Too short to produce chunks after chunking

        mock_http = _make_http_mock()
        with (
            patch.object(pipeline, "_fetch_from_minio", AsyncMock(return_value=raw)),
            patch.object(pipeline, "chunk_text", return_value=[]),  # Empty chunks
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "empty.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] == "no_chunks_produced"

    @pytest.mark.asyncio
    async def test_embedding_failure_emits_rejected(self):
        from processing import pipeline

        raw = b"Some document content. " * 20
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", AsyncMock(return_value=raw)),
            patch.object(pipeline, "embed_batch", AsyncMock(side_effect=Exception("API error"))),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "doc.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] == "embedding_failed"

    @pytest.mark.asyncio
    async def test_chunk_write_failure_emits_rejected(self):
        from processing import pipeline

        raw = b"Content for write failure test. " * 20
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", AsyncMock(return_value=raw)),
            patch.object(pipeline, "embed_batch", AsyncMock(return_value=[[0.1, 0.2]] * 2)),
            patch.object(pipeline, "write_chunks", AsyncMock(side_effect=Exception("DB write failed"))),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "doc.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] == "chunk_write_failed"


class TestGetS3Client:
    def test_get_s3_client_uses_env(self):
        from processing.pipeline import _get_s3_client

        with (
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "admin",
                "MINIO_ROOT_PASSWORD": "password",
            }),
            patch("processing.pipeline.boto3.client") as mock_boto,
        ):
            _get_s3_client()
            mock_boto.assert_called_once()


class TestFetchFromMinio:
    @pytest.mark.asyncio
    async def test_fetches_bytes_from_s3(self):
        from processing.pipeline import _fetch_from_minio

        mock_client = MagicMock()
        mock_client.get_object = MagicMock(return_value={"Body": MagicMock(read=MagicMock(return_value=b"file content"))})

        with patch("processing.pipeline._get_s3_client", return_value=mock_client):
            result = await _fetch_from_minio("test-key")

        assert result == b"file content"


# ---------------------------------------------------------------------------
# deletion.py — uncovered paths
# ---------------------------------------------------------------------------

class TestDeletionGetPool:
    def test_get_pool_raises_when_not_init(self):
        from processing import deletion

        original = deletion._pool
        try:
            deletion._pool = None
            with pytest.raises(RuntimeError, match="not initialised"):
                deletion._get_pool()
        finally:
            deletion._pool = original


class TestDeletionGetS3Client:
    def test_get_s3_client_uses_env(self):
        from processing.deletion import _get_s3_client

        with (
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "admin",
                "MINIO_ROOT_PASSWORD": "password",
            }),
            patch("processing.deletion.boto3.client") as mock_boto,
        ):
            _get_s3_client()
            mock_boto.assert_called_once()


class TestDeleteFromMinio:
    @pytest.mark.asyncio
    async def test_deletes_object_successfully(self):
        from processing.deletion import _delete_from_minio

        mock_client = MagicMock()
        mock_client.delete_object = MagicMock()

        with patch("processing.deletion._get_s3_client", return_value=mock_client):
            await _delete_from_minio("test/doc.pdf")

        mock_client.delete_object.assert_called_once_with(
            Bucket="clive-raw-store",
            Key="test/doc.pdf",
        )

    @pytest.mark.asyncio
    async def test_no_such_key_is_idempotent(self):
        from processing.deletion import _delete_from_minio
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.delete_object = MagicMock(
            side_effect=ClientError(
                error_response={"Error": {"Code": "NoSuchKey"}},
                operation_name="DeleteObject",
            )
        )

        with patch("processing.deletion._get_s3_client", return_value=mock_client):
            # Should not raise
            await _delete_from_minio("already/gone.pdf")


class TestExecuteDeletion:
    @pytest.mark.asyncio
    async def test_emits_not_found_when_no_chunks(self):
        from processing import deletion

        payload = {
            "action_request_id": "req-001",
            "action_target": "missing.pdf",
            "chat_id": 12345,
            "conversation_id": str(uuid.uuid4()),
        }

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])  # No chunks found
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_http = _make_http_mock()

        original_pool = deletion._pool
        try:
            deletion._pool = mock_pool
            # httpx is imported locally in execute_deletion, patch at httpx module level
            with patch("httpx.AsyncClient", return_value=mock_http):
                await deletion.execute_deletion(payload, "http://orchestrator:8080")
        finally:
            deletion._pool = original_pool

        post_json = mock_http.post.call_args[1]["json"]
        assert post_json["event_type"] == "deletion.not_found"

    @pytest.mark.asyncio
    async def test_emits_deletion_complete_when_found(self):
        from processing import deletion

        payload = {
            "action_request_id": "req-002",
            "action_target": "report.pdf",
            "chat_id": 12345,
            "conversation_id": str(uuid.uuid4()),
        }

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"source_key": "uid/report.pdf"}])
        mock_conn.fetchval = AsyncMock(return_value=5)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        mock_http = _make_http_mock()

        original_pool = deletion._pool
        try:
            deletion._pool = mock_pool
            with (
                patch("processing.deletion._delete_from_minio", AsyncMock()),
                patch("httpx.AsyncClient", return_value=mock_http),
            ):
                await deletion.execute_deletion(payload, "http://orchestrator:8080")
        finally:
            deletion._pool = original_pool

        post_json = mock_http.post.call_args[1]["json"]
        assert post_json["event_type"] == "deletion.complete"
        assert post_json["payload"]["chunks_removed"] == 5


# ---------------------------------------------------------------------------
# processing/main.py — HTTP handlers
# ---------------------------------------------------------------------------

class TestProcessingMainHandlers:
    @pytest.mark.asyncio
    async def test_health_endpoint_returns_ok(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from processing.main import handle_health

        app = web.Application()
        app.router.add_get("/health", handle_health)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert data["block"] == 15

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from processing.main import handle_metrics

        app = web.Application()
        app.router.add_get("/metrics", handle_metrics)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_ingest_endpoint_accepts(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from processing.main import handle_ingest

        app = web.Application()
        app.router.add_post("/ingest", handle_ingest)

        # Patch the `process` function imported into main
        with patch("processing.main.process", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/ingest", json={
                    "event_id": str(uuid.uuid4()),
                    "payload": {
                        "source_key": "uid/test.pdf",
                        "content_type": "application/pdf",
                    },
                })
                assert resp.status == 202

    @pytest.mark.asyncio
    async def test_delete_endpoint_accepts(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from processing.main import handle_delete

        app = web.Application()
        app.router.add_post("/delete", handle_delete)

        with patch("processing.main.execute_deletion", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/delete", json={
                    "event_id": str(uuid.uuid4()),
                    "payload": {
                        "action_target": "doc.pdf",
                    },
                })
                assert resp.status == 202
