"""Tests for Block 15 pipeline — happy path and rejection cases."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _make_http_mock():
    """Return an AsyncMock that behaves as an httpx.AsyncClient context manager."""
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


def _embed_side_effect(texts):
    return [[0.1, 0.2, 0.3]] * len(texts)


class TestProcessHappyPath:
    async def test_emits_ingest_processed(self):
        from processing import pipeline

        raw = b"This is a test document. " * 20
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=raw)),
            patch.object(pipeline, "embed_batch", new=AsyncMock(side_effect=_embed_side_effect)),
            patch.object(pipeline, "write_chunks", new=AsyncMock(return_value=1)),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "doc.txt", "content_type": "text/plain"})

        mock_http.post.assert_called_once()
        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.processed"

    async def test_source_block_is_15(self):
        from processing import pipeline

        raw = b"test content for block source check"
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=raw)),
            patch.object(pipeline, "embed_batch", new=AsyncMock(side_effect=_embed_side_effect)),
            patch.object(pipeline, "write_chunks", new=AsyncMock(return_value=1)),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "doc.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["source_block"] == 15

    async def test_payload_contains_source_key_and_chunk_count(self):
        from processing import pipeline

        raw = b"Document content. " * 20
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=raw)),
            patch.object(pipeline, "embed_batch", new=AsyncMock(side_effect=_embed_side_effect)),
            patch.object(pipeline, "write_chunks", new=AsyncMock(return_value=2)),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "notes.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["payload"]["source_key"] == "notes.txt"
        assert "chunk_count" in posted["payload"]
        assert "inserted_count" in posted["payload"]


class TestProcessRejection:
    async def test_file_too_large_emits_rejected(self):
        from processing import pipeline

        huge = b"x" * (pipeline.MAX_FILE_SIZE + 1)
        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=huge)),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "big.bin", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] == "file_too_large"

    async def test_minio_fetch_failure_emits_rejected(self):
        from processing import pipeline

        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(side_effect=Exception("bucket error"))),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "missing.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] == "fetch_failed"

    async def test_empty_document_emits_rejected(self):
        from processing import pipeline

        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=b"   ")),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "blank.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"

    async def test_extraction_failure_emits_rejected(self):
        from processing import pipeline

        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(return_value=b"not a pdf")),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "corrupt.pdf", "content_type": "application/pdf"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["event_type"] == "ingest.rejected"
        assert posted["payload"]["reason"] in ("extraction_failed", "no_chunks_produced")

    async def test_rejected_payload_contains_source_key(self):
        from processing import pipeline

        mock_http = _make_http_mock()

        with (
            patch.object(pipeline, "_fetch_from_minio", new=AsyncMock(side_effect=Exception("gone"))),
            patch("processing.pipeline.httpx.AsyncClient", return_value=mock_http),
        ):
            await pipeline.process({"source_key": "gone.txt", "content_type": "text/plain"})

        posted = mock_http.post.call_args[1]["json"]
        assert posted["payload"]["source_key"] == "gone.txt"
