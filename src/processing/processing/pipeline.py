"""Block 15 processing pipeline — D-099.

Receives ingest.received events from Block 13, processes documents,
and emits ingest.processed or ingest.rejected back to Block 13.

Flow:
  1. Fetch raw document from MinIO clive-raw-store bucket (MINIO_RAW_BUCKET)
  2. Reject if >10 MB (D-098, defense in depth)
  3. Extract text (PDF or plain text)
  4. Chunk at 512 tokens / 50-token overlap / 50-token minimum (D-097)
  5. Embed via LiteLLM text-embedding-3-small (D-096)
  6. Write to clive_search.chunks; ON CONFLICT DO NOTHING (D-025)
  7. Emit ingest.processed with chunk count

v0.5: prometheus_client instrumentation added (D-122 Phase 2).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from typing import Any

import boto3
import httpx
import structlog

from .chunker import chunk_text
from .embedder import embed_batch
from .extractor import extract_text
from .metrics import chunks_created_total, ingest_total, processing_duration_seconds
from .store import write_chunks

log = structlog.get_logger()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB — D-098
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8080")  # NOSONAR — Docker-internal, no TLS
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")  # NOSONAR — Docker-internal, no TLS
MINIO_BUCKET = os.environ.get("MINIO_RAW_BUCKET", "clive-raw-store")
EMBED_BATCH_SIZE = 32
_EVENT_INGEST_REJECTED = "ingest.rejected"


def _get_s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    )


async def _fetch_from_minio(source_key: str) -> bytes:
    loop = asyncio.get_running_loop()

    def _get() -> bytes:
        client = _get_s3_client()
        response = client.get_object(Bucket=MINIO_BUCKET, Key=source_key)
        return response["Body"].read()

    return await loop.run_in_executor(None, _get)


async def _emit(event_type: str, payload: dict[str, Any]) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ORCHESTRATOR_URL}/events",
            json={"event_type": event_type, "source_block": 15, **payload},
            timeout=10.0,
        )


def _content_hashes(chunks: list[str]) -> list[str]:
    return [hashlib.sha256(c.encode()).hexdigest() for c in chunks]


async def process(event_payload: dict[str, Any]) -> None:
    """Process one ingest.received event payload."""
    source_key = event_payload["source_key"]
    content_type = event_payload.get("content_type", "text/plain")
    conversation_id = event_payload.get("conversation_id")
    chat_id = event_payload.get("chat_id")          # D-103 criterion 6 provenance
    event_id = str(uuid.uuid4())

    start_time = time.monotonic()

    log.info("processing_start", source_key=source_key)

    try:
        raw_bytes = await _fetch_from_minio(source_key)
    except Exception as exc:
        log.error("minio_fetch_failed", source_key=source_key, error=str(exc))
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {"source_key": source_key, "reason": "fetch_failed", "detail": str(exc)},
        })
        return

    # D-098 defense-in-depth size check
    if len(raw_bytes) > MAX_FILE_SIZE:
        log.warning("file_too_large", source_key=source_key, size=len(raw_bytes))
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {
                "source_key": source_key,
                "reason": "file_too_large",
                "file_size": len(raw_bytes),             # D-103 criterion 6 provenance
            },
        })
        return

    try:
        text = extract_text(raw_bytes, content_type, source_key)
    except ValueError as exc:
        log.error("extraction_failed", source_key=source_key, error=str(exc))
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {"source_key": source_key, "reason": "extraction_failed", "detail": str(exc)},
        })
        return

    chunks = chunk_text(text)
    if not chunks:
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {"source_key": source_key, "reason": "no_chunks_produced"},
        })
        return

    hashes = _content_hashes(chunks)

    # Embed in batches — wrapped so a LiteLLM/API failure emits ingest.rejected
    # rather than dying silently inside asyncio.create_task.
    try:
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            batch_embeddings = await embed_batch(batch)
            embeddings.extend(batch_embeddings)
    except Exception as exc:
        log.error("embedding_failed", source_key=source_key, error=str(exc))
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {
                "source_key": source_key,
                "reason": "embedding_failed",
                "detail": str(exc),
                "file_size": len(raw_bytes),
                "chat_id": chat_id,
            },
        })
        return

    try:
        inserted = await write_chunks(
            chunks=chunks,
            embeddings=embeddings,
            source_key=source_key,
            content_hashes=hashes,
        )
    except Exception as exc:
        log.error("chunk_write_failed", source_key=source_key, error=str(exc))
        ingest_total.labels(status="rejected").inc()
        processing_duration_seconds.observe(time.monotonic() - start_time)
        await _emit(_EVENT_INGEST_REJECTED, {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "payload": {
                "source_key": source_key,
                "reason": "chunk_write_failed",
                "detail": str(exc),
                "file_size": len(raw_bytes),
                "chat_id": chat_id,
            },
        })
        return

    log.info("processing_complete", source_key=source_key, chunks=len(chunks), inserted=inserted)

    # Record success metrics (D-122 Phase 2)
    ingest_total.labels(status="processed").inc()
    chunks_created_total.inc(inserted)
    processing_duration_seconds.observe(time.monotonic() - start_time)

    await _emit("ingest.processed", {
        "event_id": event_id,
        "conversation_id": conversation_id,
        "payload": {
            "source_key": source_key,
            "chunk_count": len(chunks),
            "inserted_count": inserted,
            "file_size": len(raw_bytes),                 # D-103 criterion 6 provenance
            "chat_id": chat_id,                          # D-103 criterion 6 provenance
        },
    })
