"""Tests for T8 — Deletion pipeline.

D-025: idempotent — already-deleted document succeeds gracefully.
D-006: only executes after Block 9 confirms.
D-106 criterion 4: not-found → clear event, no crash.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


ORCHESTRATOR_URL = "http://orchestrator:8080"  # NOSONAR — Docker-internal, no TLS


def _make_payload(
    filename: str = "report.pdf",
    chat_id: int = 12345,
    action_request_id: str | None = None,
) -> dict:
    return {
        "action_request_id": action_request_id or str(uuid.uuid4()),
        "action_type": "document.delete",
        "action_target": filename,
        "action_description": f"Delete {filename}.",
        "chat_id": chat_id,
        "conversation_id": str(uuid.uuid4()),
    }


@pytest.fixture
def mock_pool_with_rows():
    """Pool that returns rows for source_key lookup."""

    def _make(rows):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.fetchval = AsyncMock(return_value=len(rows))
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)
        pool = AsyncMock()
        pool.acquire = MagicMock(return_value=conn)
        return pool, conn

    return _make


@pytest.mark.asyncio
async def test_deletion_not_found_emits_not_found_event(mock_pool_with_rows):
    """When no chunks found for filename, emit deletion.not_found."""
    pool, _ = mock_pool_with_rows([])

    posted_events = []

    def mock_post(url, json, **kwargs):  # noqa: ARG001
        posted_events.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    with patch("processing.deletion._pool", pool), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client_cls.return_value = mock_client

        from processing.deletion import execute_deletion
        payload = _make_payload("nonexistent.pdf")
        await execute_deletion(payload, ORCHESTRATOR_URL)

    assert len(posted_events) == 1
    assert posted_events[0]["event_type"] == "deletion.not_found"
    assert posted_events[0]["payload"]["filename"] == "nonexistent.pdf"


@pytest.mark.asyncio
async def test_deletion_found_emits_complete_event(mock_pool_with_rows):
    """When chunks exist, delete them and emit deletion.complete."""
    source_key = f"{uuid.uuid4()}/report.pdf"
    pool, conn = mock_pool_with_rows([{"source_key": source_key}])
    conn.fetchval = AsyncMock(return_value=5)  # 5 chunks deleted

    posted_events = []

    def mock_post(url, json, **kwargs):  # noqa: ARG001
        posted_events.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    with patch("processing.deletion._pool", pool), \
         patch("processing.deletion._delete_from_minio", new_callable=AsyncMock), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client_cls.return_value = mock_client

        from processing.deletion import execute_deletion
        payload = _make_payload("report.pdf")
        await execute_deletion(payload, ORCHESTRATOR_URL)

    assert len(posted_events) == 1
    assert posted_events[0]["event_type"] == "deletion.complete"
    assert posted_events[0]["payload"]["filename"] == "report.pdf"
    assert posted_events[0]["payload"]["chunks_removed"] == 5


@pytest.mark.asyncio
async def test_deletion_idempotent_zero_chunks(mock_pool_with_rows):
    """D-025: if chunks already gone (0 deleted), still emit deletion.complete."""
    source_key = f"{uuid.uuid4()}/report.pdf"
    pool, conn = mock_pool_with_rows([{"source_key": source_key}])
    conn.fetchval = AsyncMock(return_value=0)  # Already deleted

    posted_events = []

    def mock_post(url, json, **kwargs):  # noqa: ARG001
        posted_events.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    with patch("processing.deletion._pool", pool), \
         patch("processing.deletion._delete_from_minio", new_callable=AsyncMock), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client_cls.return_value = mock_client

        from processing.deletion import execute_deletion
        payload = _make_payload("report.pdf")
        await execute_deletion(payload, ORCHESTRATOR_URL)

    # Should succeed, not crash
    assert len(posted_events) == 1
    assert posted_events[0]["event_type"] == "deletion.complete"
    assert posted_events[0]["payload"]["chunks_removed"] == 0


@pytest.mark.asyncio
async def test_deletion_minio_failure_does_not_abort(mock_pool_with_rows):
    """MinIO error must not abort — chunks already cleaned from DB."""
    source_key = f"{uuid.uuid4()}/report.pdf"
    pool, conn = mock_pool_with_rows([{"source_key": source_key}])
    conn.fetchval = AsyncMock(return_value=3)

    posted_events = []

    def mock_post(url, json, **kwargs):  # noqa: ARG001
        posted_events.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    async def failing_minio(source_key):  # noqa: ARG001
        raise RuntimeError("MinIO connection refused")

    with patch("processing.deletion._pool", pool), \
         patch("processing.deletion._delete_from_minio", side_effect=failing_minio), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client_cls.return_value = mock_client

        from processing.deletion import execute_deletion
        payload = _make_payload("report.pdf")
        await execute_deletion(payload, ORCHESTRATOR_URL)

    # Still emits deletion.complete — DB is the authoritative store
    assert len(posted_events) == 1
    assert posted_events[0]["event_type"] == "deletion.complete"


@pytest.mark.asyncio
async def test_deletion_complete_includes_provenance(mock_pool_with_rows):
    """D-067: deletion.complete payload must include action_request_id."""
    source_key = f"{uuid.uuid4()}/report.pdf"
    pool, conn = mock_pool_with_rows([{"source_key": source_key}])
    conn.fetchval = AsyncMock(return_value=2)

    action_request_id = str(uuid.uuid4())
    posted_events = []

    def mock_post(url, json, **kwargs):  # noqa: ARG001
        posted_events.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    with patch("processing.deletion._pool", pool), \
         patch("processing.deletion._delete_from_minio", new_callable=AsyncMock), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client_cls.return_value = mock_client

        from processing.deletion import execute_deletion
        payload = _make_payload("report.pdf", action_request_id=action_request_id)
        await execute_deletion(payload, ORCHESTRATOR_URL)

    assert posted_events[0]["payload"]["action_request_id"] == action_request_id
