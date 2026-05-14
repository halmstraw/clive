"""T8 — Deletion pipeline for Block 16 (v0.3).

Executes document deletion after Block 9 confirms the action.

Flow (called from main.py /delete endpoint):
  1. Receive action.confirmed payload with action_target = source_key pattern
  2. Look up matching chunks in clive_search.chunks
  3. If no chunks found: emit deletion.not_found to Block 13 (D-106 criterion 4)
  4. Delete all matching chunks (idempotent, D-025)
  5. Delete raw file from MinIO clive-raw-store (idempotent on not-found)
  6. Emit deletion.complete to Block 13

D-025 idempotency: if chunks are already gone and MinIO object already absent,
report success — not an error. At-least-once delivery means this handler
may be called twice for the same confirmed action.

D-067: deletion events are audited by Block 13 when emitted back as events.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import asyncpg
import boto3
import structlog
from botocore.exceptions import ClientError

log = structlog.get_logger()

MINIO_BUCKET = os.environ.get("MINIO_RAW_BUCKET", "clive-raw-store")

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the deletion DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, statement_cache_size=0)
    log.info("deletion_pool_initialised")


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Deletion pool not initialised")
    return _pool


def _get_s3_client() -> Any:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    )


async def _delete_from_minio(source_key: str) -> None:
    """Delete a single object from MinIO. Idempotent — not-found is not an error."""
    loop = asyncio.get_running_loop()

    def _do_delete() -> None:
        client = _get_s3_client()
        try:
            client.delete_object(Bucket=MINIO_BUCKET, Key=source_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            # NoSuchKey is the idempotent case — object already gone
            if code in ("NoSuchKey", "404"):
                log.info("minio_object_already_absent", source_key=source_key)
                return
            raise

    await loop.run_in_executor(None, _do_delete)
    log.info("minio_object_deleted", source_key=source_key)


async def execute_deletion(payload: dict[str, Any], orchestrator_url: str) -> None:
    """Execute T8 deletion pipeline.

    payload contains:
      action_request_id  — correlation ID from Block 9
      action_target      — filename (original name, e.g. "report.pdf")
      action_type        — should be "document.delete"
      chat_id            — for surface routing
      conversation_id    — for Block 13 routing
      suppress_telegram  — if True, propagated to result events so Block 23
                           skips the Telegram send (used by E2E test suite)

    Matching strategy (D-109): source_key format is {uuid}/{original_filename}.
    We match WHERE source_key LIKE '%/' || filename.
    """
    import httpx  # noqa: PLC0415 — avoids circular import at module level

    action_request_id = payload.get("action_request_id", "")
    filename = payload.get("action_target", "")
    chat_id = payload.get("chat_id")
    conversation_id = payload.get("conversation_id")
    suppress_telegram = bool(payload.get("suppress_telegram", False))

    log.info(
        "deletion_pipeline_start",
        action_request_id=action_request_id,
        filename=filename,
    )

    pool = _get_pool()
    async with pool.acquire() as conn:
        # Find all source_keys matching this filename (D-109)
        rows = await conn.fetch(
            """
            SELECT DISTINCT source_key
            FROM clive_search.chunks
            WHERE source_key LIKE '%/' || $1
            AND zone_of_origin = 'personal'
            """,
            filename,
        )

    if not rows:
        # D-106 criterion 4: document not found → clear message, no crash
        log.info(
            "deletion_not_found",
            filename=filename,
            action_request_id=action_request_id,
        )
        event_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{orchestrator_url}/events",
                json={
                    "event_type": "deletion.not_found",
                    "source_block": 15,
                    "event_id": event_id,
                    "conversation_id": conversation_id,
                    "payload": {
                        "action_request_id": action_request_id,
                        "filename": filename,
                        "chat_id": chat_id,
                        "suppress_telegram": suppress_telegram,
                    },
                },
                timeout=10.0,
            )
        return

    # Delete chunks and MinIO objects for all matching source_keys (D-025 idempotent)
    total_chunks_removed = 0
    source_keys_deleted = [row["source_key"] for row in rows]

    async with pool.acquire() as conn:
        for source_key in source_keys_deleted:
            result = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM clive_search.chunks
                    WHERE source_key = $1
                    RETURNING chunk_id
                )
                SELECT count(*) FROM deleted
                """,
                source_key,
            )
            total_chunks_removed += int(result or 0)
            log.info(
                "chunks_deleted",
                source_key=source_key,
                count=int(result or 0),
            )

    # Delete MinIO objects (idempotent — already-absent is OK)
    for source_key in source_keys_deleted:
        try:
            await _delete_from_minio(source_key)
        except Exception as exc:
            # Log but don't abort — chunks are gone, MinIO removal is best-effort
            # The critical data store (DB) is already clean.
            log.error(
                "minio_deletion_error",
                source_key=source_key,
                error=str(exc),
            )

    # Emit deletion.complete to Block 13
    event_id = str(uuid.uuid4())
    log.info(
        "deletion_complete",
        filename=filename,
        source_keys_count=len(source_keys_deleted),
        total_chunks_removed=total_chunks_removed,
        action_request_id=action_request_id,
    )
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{orchestrator_url}/events",
            json={
                "event_type": "deletion.complete",
                "source_block": 15,
                "event_id": event_id,
                "conversation_id": conversation_id,
                "payload": {
                    "action_request_id": action_request_id,
                    "filename": filename,
                    "source_keys_deleted": source_keys_deleted,
                    "chunks_removed": total_chunks_removed,
                    "chat_id": chat_id,
                    "suppress_telegram": suppress_telegram,
                },
            },
            timeout=10.0,
        )
