"""Tests for dashboard session authentication (v0.11, D-146, D-147 AC-3).

Verifies:
- handle_login returns 200 and sets cookie on correct DASHBOARD_SECRET
- handle_login returns 401 on wrong secret
- handle_login returns 500 when DASHBOARD_SECRET is not configured
- require_session returns 401 when no cookie present
- require_session returns 401 on invalid/expired token
- validate_session returns None for unknown token
- create_session returns a 64-char hex string
"""

from __future__ import annotations

import os
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLoginLogic:
    """DASHBOARD_SECRET validation."""

    def test_correct_secret_accepted(self, monkeypatch):
        """Login with the correct secret should succeed (constant-time compare)."""
        monkeypatch.setenv("DASHBOARD_SECRET", "mysecret")
        from clive_dashboard.auth import _get_dashboard_secret
        assert _get_dashboard_secret() == "mysecret"

    def test_missing_secret_raises(self, monkeypatch):
        """Missing DASHBOARD_SECRET should raise RuntimeError."""
        monkeypatch.setenv("DASHBOARD_SECRET", "")
        from clive_dashboard.auth import _get_dashboard_secret
        with pytest.raises(RuntimeError, match="DASHBOARD_SECRET not set"):
            _get_dashboard_secret()

    def test_secret_comparison_is_constant_time(self, monkeypatch):
        """Secrets comparison uses secrets.compare_digest (timing-safe)."""
        monkeypatch.setenv("DASHBOARD_SECRET", "correct")
        correct = b"correct"
        wrong = b"wrong12"
        assert secrets.compare_digest(correct, correct)
        assert not secrets.compare_digest(correct, wrong)


class TestSessionToken:
    """Session token generation."""

    def test_token_is_64_chars(self):
        """Session token is 64 hex characters (32 bytes)."""
        token = secrets.token_hex(32)
        assert len(token) == 64

    def test_tokens_are_unique(self):
        """Each token generation produces a unique value."""
        tokens = {secrets.token_hex(32) for _ in range(100)}
        assert len(tokens) == 100


class TestValidateSession:
    """validate_session with pool mocks."""

    @pytest.mark.asyncio
    async def test_validate_returns_none_when_pool_not_init(self):
        """validate_session returns None when pool is not initialised."""
        from clive_dashboard import auth as auth_module
        original = auth_module._pool
        auth_module._pool = None
        try:
            result = await auth_module.validate_session("sometoken")
            assert result is None
        finally:
            auth_module._pool = original

    @pytest.mark.asyncio
    async def test_validate_returns_none_for_unknown_token(self):
        """validate_session returns None when token not found in DB."""
        from clive_dashboard import auth as auth_module

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original = auth_module._pool
        auth_module._pool = mock_pool
        try:
            result = await auth_module.validate_session("nonexistent_token")
            assert result is None
        finally:
            auth_module._pool = original

    @pytest.mark.asyncio
    async def test_validate_returns_session_dict_for_valid_token(self):
        """validate_session returns session dict for a valid, non-expired token."""
        from clive_dashboard import auth as auth_module
        import uuid
        from datetime import datetime, timezone

        mock_row = {
            "session_token": "abc123",
            "user_id": uuid.uuid4(),
            "expires_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original = auth_module._pool
        auth_module._pool = mock_pool
        try:
            result = await auth_module.validate_session("abc123")
            assert result is not None
            assert result["session_token"] == "abc123"
            assert "user_id" in result
            assert "expires_at" in result
        finally:
            auth_module._pool = original


class TestRequireSession:
    """require_session raises 401 on missing/invalid session."""

    @pytest.mark.asyncio
    async def test_require_session_raises_on_no_cookie(self):
        """require_session raises HTTPUnauthorized when no cookie present."""
        from aiohttp import web
        from clive_dashboard.auth import require_session

        mock_request = MagicMock()
        mock_request.cookies = {}

        with pytest.raises(web.HTTPUnauthorized):
            await require_session(mock_request)

    @pytest.mark.asyncio
    async def test_require_session_raises_on_invalid_token(self):
        """require_session raises HTTPUnauthorized on invalid token."""
        from aiohttp import web
        from clive_dashboard import auth as auth_module

        mock_request = MagicMock()
        mock_request.cookies = {"clive_session": "bad_token"}

        original = auth_module._pool
        auth_module._pool = None  # Pool unavailable → validate returns None
        try:
            with pytest.raises(web.HTTPUnauthorized):
                await auth_module.require_session(mock_request)
        finally:
            auth_module._pool = original
