"""Extended tests for dashboard auth.py and main.py."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


# ---------------------------------------------------------------------------
# auth.py helpers
# ---------------------------------------------------------------------------

def _make_pool_with_conn(conn: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool


# ---------------------------------------------------------------------------
# _get_owner_user_id (lines 65-71)
# ---------------------------------------------------------------------------

class TestGetOwnerUserId:
    @pytest.mark.asyncio
    async def test_returns_none_when_pool_not_init(self):
        from clive_dashboard import auth

        original = auth._pool
        try:
            auth._pool = None
            result = await auth._get_owner_user_id()
            assert result is None
        finally:
            auth._pool = original

    @pytest.mark.asyncio
    async def test_returns_uuid_when_owner_found(self):
        from clive_dashboard import auth

        uid = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"user_id": uid})

        original = auth._pool
        try:
            auth._pool = _make_pool_with_conn(mock_conn)
            result = await auth._get_owner_user_id()
            assert result == uid
        finally:
            auth._pool = original

    @pytest.mark.asyncio
    async def test_returns_none_when_no_owner(self):
        from clive_dashboard import auth

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        original = auth._pool
        try:
            auth._pool = _make_pool_with_conn(mock_conn)
            result = await auth._get_owner_user_id()
            assert result is None
        finally:
            auth._pool = original


# ---------------------------------------------------------------------------
# create_session (lines 80-102)
# ---------------------------------------------------------------------------

class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session_token(self):
        from clive_dashboard import auth

        uid = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        original = auth._pool
        try:
            auth._pool = _make_pool_with_conn(mock_conn)
            token = await auth.create_session(uid)
            assert len(token) == 64  # 32 bytes hex
            assert mock_conn.execute.call_count == 2  # DELETE + INSERT
        finally:
            auth._pool = original

    @pytest.mark.asyncio
    async def test_raises_when_pool_not_init(self):
        from clive_dashboard import auth

        original = auth._pool
        try:
            auth._pool = None
            with pytest.raises(RuntimeError, match="Auth pool not initialised"):
                await auth.create_session(uuid.uuid4())
        finally:
            auth._pool = original


# ---------------------------------------------------------------------------
# validate_session (lines 105-136) — extend existing test_v11_dashboard_auth.py
# ---------------------------------------------------------------------------

class TestValidateSession:
    @pytest.mark.asyncio
    async def test_returns_none_when_pool_not_init(self):
        from clive_dashboard import auth

        original = auth._pool
        try:
            auth._pool = None
            result = await auth.validate_session("test-token")
            assert result is None
        finally:
            auth._pool = original

    @pytest.mark.asyncio
    async def test_returns_session_dict_on_valid_token(self):
        from clive_dashboard import auth

        uid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_row = {
            "session_token": "test-token",
            "user_id": uid,
            "expires_at": now,
            "created_at": now,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.execute = AsyncMock()

        original = auth._pool
        try:
            auth._pool = _make_pool_with_conn(mock_conn)
            result = await auth.validate_session("test-token")
        finally:
            auth._pool = original

        assert result is not None
        assert result["session_token"] == "test-token"
        assert result["user_id"] == str(uid)


# ---------------------------------------------------------------------------
# invalidate_session (lines 141-148)
# ---------------------------------------------------------------------------

class TestInvalidateSession:
    @pytest.mark.asyncio
    async def test_returns_early_when_pool_not_init(self):
        from clive_dashboard import auth

        original = auth._pool
        try:
            auth._pool = None
            # Should not raise
            await auth.invalidate_session("test-token")
        finally:
            auth._pool = original

    @pytest.mark.asyncio
    async def test_deletes_session_from_db(self):
        from clive_dashboard import auth

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        original = auth._pool
        try:
            auth._pool = _make_pool_with_conn(mock_conn)
            await auth.invalidate_session("test-token")
            mock_conn.execute.assert_called_once()
        finally:
            auth._pool = original


# ---------------------------------------------------------------------------
# require_session — valid session returns session dict (line 165)
# ---------------------------------------------------------------------------

class TestRequireSession:
    @pytest.mark.asyncio
    async def test_returns_session_on_valid_cookie(self):
        from clive_dashboard.auth import require_session

        mock_request = MagicMock()
        mock_request.cookies = {"clive_session": "valid-token"}

        mock_session = {"session_token": "valid-token", "user_id": str(uuid.uuid4())}

        with patch("clive_dashboard.auth.validate_session", AsyncMock(return_value=mock_session)):
            result = await require_session(mock_request)

        assert result == mock_session


# ---------------------------------------------------------------------------
# handle_login (lines 175-217)
# ---------------------------------------------------------------------------

async def _make_auth_app() -> web.Application:
    from clive_dashboard.auth import handle_login, handle_logout

    app = web.Application()
    app.router.add_post("/auth/login", handle_login)
    app.router.add_post("/auth/logout", handle_logout)
    return app


class TestHandleLogin:
    @pytest.mark.asyncio
    async def test_login_success_sets_cookie(self):
        app = await _make_auth_app()
        uid = uuid.uuid4()

        with (
            patch.dict("os.environ", {"DASHBOARD_SECRET": "correct-secret"}),
            patch("clive_dashboard.auth._get_owner_user_id", AsyncMock(return_value=uid)),
            patch("clive_dashboard.auth.create_session", AsyncMock(return_value="session-token")),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/auth/login", json={"secret": "correct-secret"})
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ok"
                assert "clive_session" in resp.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_secret_returns_401(self):
        app = await _make_auth_app()

        with patch.dict("os.environ", {"DASHBOARD_SECRET": "correct-secret"}):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/auth/login", json={"secret": "wrong-secret"})
                assert resp.status == 401

    @pytest.mark.asyncio
    async def test_login_invalid_json_returns_400(self):
        app = await _make_auth_app()

        with patch.dict("os.environ", {"DASHBOARD_SECRET": "correct-secret"}):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post(
                    "/auth/login",
                    data="not-json",
                    headers={"Content-Type": "application/json"},
                )
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_login_no_owner_user_returns_500(self):
        app = await _make_auth_app()

        with (
            patch.dict("os.environ", {"DASHBOARD_SECRET": "correct-secret"}),
            patch("clive_dashboard.auth._get_owner_user_id", AsyncMock(return_value=None)),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/auth/login", json={"secret": "correct-secret"})
                assert resp.status == 500

    @pytest.mark.asyncio
    async def test_login_secret_not_configured_returns_500(self):
        app = await _make_auth_app()
        import os
        os.environ.pop("DASHBOARD_SECRET", None)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/auth/login", json={"secret": "anything"})
            assert resp.status == 500

    @pytest.mark.asyncio
    async def test_login_session_create_failure_returns_500(self):
        app = await _make_auth_app()
        uid = uuid.uuid4()

        with (
            patch.dict("os.environ", {"DASHBOARD_SECRET": "secret"}),
            patch("clive_dashboard.auth._get_owner_user_id", AsyncMock(return_value=uid)),
            patch("clive_dashboard.auth.create_session", AsyncMock(side_effect=RuntimeError("pool down"))),
        ):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/auth/login", json={"secret": "secret"})
                assert resp.status == 500


# ---------------------------------------------------------------------------
# handle_logout (lines 222-228)
# ---------------------------------------------------------------------------

class TestHandleLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self):
        app = await _make_auth_app()

        with patch("clive_dashboard.auth.invalidate_session", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                # Set a session cookie first
                client.session.cookie_jar.update_cookies({"clive_session": "my-token"})
                resp = await client.post("/auth/logout")
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_logout_without_cookie_still_returns_ok(self):
        app = await _make_auth_app()

        with patch("clive_dashboard.auth.invalidate_session", AsyncMock()):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/auth/logout")
                assert resp.status == 200


# ---------------------------------------------------------------------------
# main.py — handle_health, handle_index
# ---------------------------------------------------------------------------

class TestDashboardMainHandlers:
    @pytest.mark.asyncio
    async def test_handle_health_returns_ok(self):
        from clive_dashboard.main import handle_health

        app = web.Application()
        app.router.add_get("/health", handle_health)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert data["block"] == 2

    @pytest.mark.asyncio
    async def test_handle_index_not_found_returns_404(self):
        from clive_dashboard.main import handle_index

        app = web.Application()
        app.router.add_get("/", handle_index)

        with patch("clive_dashboard.main.STATIC_DIR", __import__("pathlib").Path("/nonexistent/path")):
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/")
                assert resp.status == 404


class TestDashboardMainStartup:
    @pytest.mark.asyncio
    async def test_main_startup_and_shutdown(self):
        from clive_dashboard import main as main_mod

        real_stop = __import__("asyncio").Event()
        real_stop.set()  # Immediately stop

        mock_runner = AsyncMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()

        mock_site = AsyncMock()
        mock_site.start = AsyncMock()

        with (
            patch("clive_dashboard.main.auth.init_pool", AsyncMock()),
            patch("clive_dashboard.main.web.AppRunner", return_value=mock_runner),
            patch("clive_dashboard.main.web.TCPSite", return_value=mock_site),
            patch("clive_dashboard.main.asyncio.Event", return_value=real_stop),
            patch("clive_dashboard.main.asyncio.get_running_loop", return_value=MagicMock(
                add_signal_handler=MagicMock()
            )),
        ):
            await main_mod.main()

        mock_runner.setup.assert_called_once()
        mock_site.start.assert_called_once()
        mock_runner.cleanup.assert_called_once()
