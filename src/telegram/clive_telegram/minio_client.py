"""MinIO client for Block 14 raw document upload.

Uploads inbound files to the clive-raw-store bucket so Block 15 can fetch them.
If the bucket does not exist, raises a clear error — bucket creation is a
bootstrap prerequisite (D-094 T9, D-099 criterion 4).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import boto3
import structlog
from botocore.exceptions import ClientError

log = structlog.get_logger()

MINIO_BUCKET = os.environ.get("MINIO_RAW_BUCKET", "clive-raw-store")


def _get_s3_client() -> Any:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")  # NOSONAR — Docker-internal, no TLS
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    )


async def upload_document(source_key: str, data: bytes, content_type: str) -> None:
    """Upload raw document bytes to clive-raw-store bucket.

    Raises RuntimeError if the bucket does not exist — this is a bootstrap
    prerequisite that must be resolved by the operator, not silently created.
    """
    loop = asyncio.get_running_loop()

    def _put() -> None:
        client = _get_s3_client()
        try:
            client.put_object(
                Bucket=MINIO_BUCKET,
                Key=source_key,
                Body=data,
                ContentType=content_type,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchBucket", "404"):
                raise RuntimeError(
                    f"MinIO bucket '{MINIO_BUCKET}' does not exist. "
                    "Run the bootstrap step to create it before ingesting documents."
                ) from exc
            raise

    await loop.run_in_executor(None, _put)
    log.info("document_uploaded", source_key=source_key, size=len(data))
