"""Tests for telegram session.py, db.py, and minio_client.py."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# session.py — SessionManager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_get_or_create_returns_new_uuid(self):
        from clive_telegram.session import SessionManager

        sm = SessionManager()
        cid = sm.get_or_create(12345)
        assert isinstance(cid, uuid.UUID)

    def test_get_or_create_returns_same_uuid_on_second_call(self):
        from clive_telegram.session import SessionManager

        sm = SessionManager()
        cid1 = sm.get_or_create(12345)
        cid2 = sm.get_or_create(12345)
        assert cid1 == cid2

    def test_get_or_create_different_chats_different_uuids(self):
        from clive_telegram.session import SessionManager

        sm = SessionManager()
        cid1 = sm.get_or_create(11111)
        cid2 = sm.get_or_create(22222)
        assert cid1 != cid2

    def test_reset_returns_new_uuid(self):
        from clive_telegram.session import SessionManager

        sm = SessionManager()
        cid1 = sm.get_or_create(12345)
        cid2 = sm.reset(12345)
        assert cid1 != cid2
        assert isinstance(cid2, uuid.UUID)

    def test_reset_then_get_returns_new_uuid(self):
        from clive_telegram.session import SessionManager

        sm = SessionManager()
        sm.get_or_create(12345)
        reset_cid = sm.reset(12345)
        get_cid = sm.get_or_create(12345)
        assert reset_cid == get_cid

    def test_module_singleton_exists(self):
        from clive_telegram.session import sessions
        from clive_telegram.session import SessionManager

        assert isinstance(sessions, SessionManager)


# ---------------------------------------------------------------------------
# db.py
# ---------------------------------------------------------------------------

class TestTelegramDb:
    def test_get_pool_raises_when_not_init(self):
        from clive_telegram import db

        original = db._pool
        try:
            db._pool = None
            with pytest.raises(RuntimeError, match="DB pool not initialised"):
                db.get_pool()
        finally:
            db._pool = original

    def test_get_pool_returns_pool_when_set(self):
        from clive_telegram import db

        original = db._pool
        try:
            mock_pool = MagicMock()
            db._pool = mock_pool
            result = db.get_pool()
            assert result is mock_pool
        finally:
            db._pool = original


# ---------------------------------------------------------------------------
# minio_client.py
# ---------------------------------------------------------------------------

class TestMinioClient:
    @pytest.mark.asyncio
    async def test_upload_document_success(self):
        from clive_telegram.minio_client import upload_document

        mock_client = MagicMock()
        mock_client.put_object = MagicMock()

        with (
            patch("clive_telegram.minio_client._get_s3_client", return_value=mock_client),
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "admin",
                "MINIO_ROOT_PASSWORD": "password",
            }),
        ):
            await upload_document("raw/doc.pdf", b"content bytes", "application/pdf")

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "raw/doc.pdf"
        assert call_kwargs["Body"] == b"content bytes"

    @pytest.mark.asyncio
    async def test_upload_raises_runtime_error_when_bucket_missing(self):
        from clive_telegram.minio_client import upload_document
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.put_object.side_effect = ClientError(
            error_response={"Error": {"Code": "NoSuchBucket"}},
            operation_name="PutObject",
        )

        with (
            patch("clive_telegram.minio_client._get_s3_client", return_value=mock_client),
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "admin",
                "MINIO_ROOT_PASSWORD": "password",
            }),
            pytest.raises(RuntimeError, match="does not exist"),
        ):
            await upload_document("raw/doc.pdf", b"bytes", "application/pdf")

    @pytest.mark.asyncio
    async def test_upload_reraises_other_client_errors(self):
        from clive_telegram.minio_client import upload_document
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.put_object.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name="PutObject",
        )

        with (
            patch("clive_telegram.minio_client._get_s3_client", return_value=mock_client),
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "admin",
                "MINIO_ROOT_PASSWORD": "password",
            }),
            pytest.raises(ClientError),
        ):
            await upload_document("raw/doc.pdf", b"bytes", "application/pdf")

    def test_get_s3_client_uses_env_vars(self):
        from clive_telegram.minio_client import _get_s3_client

        with (
            patch("clive_telegram.minio_client.boto3.client") as mock_boto,
            patch.dict("os.environ", {
                "MINIO_ROOT_USER": "testuser",
                "MINIO_ROOT_PASSWORD": "testpass",
                "MINIO_ENDPOINT": "http://minio:9000",
            }),
        ):
            _get_s3_client()

        mock_boto.assert_called_once()
        call_kwargs = mock_boto.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "testuser"
        assert call_kwargs["aws_secret_access_key"] == "testpass"
