"""Block 2 — Web dashboard session authentication (v0.11, D-146).

D-147 AC-3: owner logs in with DASHBOARD_SECRET from secrets.env.
On correct secret: 32-byte hex session token issued, stored in
clive_state.web_sessions, returned as an HTTP-only cookie.

All /api/* endpoints call require_session() which checks the cookie
against clive_state.web_sessions. Expired sessions return HTTP 401.

D-001: single-owner system. The session is linked to the owner user record
in clive_state.users (role='owner'). No multi-user login exposed.

D-057: channel-as-authentication extended for web surface.
The secret takes the place of channel membership as the authentication factor.

Fail behaviour:
- DB pool unavailable: auth fails closed (401, not fail-open).
  Dashboard auth must not grant access when DB is unreachable.
  This differs from Block 23 auth which fails open (Telegram is mission-critical;
  dashboard is supplementary).
"""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog
from aiohttp import web

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None
SESSION_COOKIE = "clive_session"
SESSION_EXPIRY_DAYS = 30


async def init_pool() -> None:
    """Initialise dashboard auth DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    log.info("dashboard_auth_pool_initialised")


def _get_dashboard_secret() -> str:
    """Return DASHBOARD_SECRET from environment. Raises if not set."""
    secret = os.environ.get("DASHBOARD_SECRET", "")
    if not secret:
        raise RuntimeError("DASHBOARD_SECRET not set in environment")
    return secret


async def _get_owner_user_id() -> uuid.UUID | None:
    """Look up the owner's user_id from clive_state.users.

    Returns None if pool unavailable or no owner record found.
    """
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM clive_state.users WHERE role = 'owner' LIMIT 1"
        )
    return uuid.UUID(str(row["user_id"])) if row else None


async def create_session(user_id: uuid.UUID) -> str:
    """Create a new session token and store it in clive_state.web_sessions.

    Returns the session token string (64-character hex).
    Raises RuntimeError if pool is unavailable.
    """
    if _pool is None:
        raise RuntimeError("Auth pool not initialised")

    token = secrets.token_hex(32)  # 64-char hex = 32 bytes entropy
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=SESSION_EXPIRY_DAYS)

    async with _pool.acquire() as conn:
        # Clean up expired sessions for this user first
        await conn.execute(
            "DELETE FROM clive_state.web_sessions WHERE expires_at < NOW()"
        )
        await conn.execute(
            """
            INSERT INTO clive_state.web_sessions (session_token, user_id, expires_at)
            VALUES ($1, $2, $3)
            """,
            token,
            user_id,
            expires_at,
        )

    log.info("session_created", user_id=str(user_id))
    return token


async def validate_session(token: str) -> dict | None:
    """Validate session token against clive_state.web_sessions.

    Updates last_seen_at on valid tokens.
    Returns session row dict on valid token, None on invalid or expired.
    """
    if _pool is None:
        return None

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT session_token, user_id, expires_at, created_at
            FROM clive_state.web_sessions
            WHERE session_token = $1 AND expires_at > NOW()
            """,
            token,
        )
        if row:
            await conn.execute(
                "UPDATE clive_state.web_sessions SET last_seen_at = NOW() WHERE session_token = $1",
                token,
            )

    if not row:
        return None

    return {
        "session_token": row["session_token"],
        "user_id": str(row["user_id"]),
        "expires_at": row["expires_at"].isoformat(),
    }


async def invalidate_session(token: str) -> None:
    """Delete a session (logout)."""
    if _pool is None:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM clive_state.web_sessions WHERE session_token = $1",
            token,
        )
    log.info("session_invalidated")


async def require_session(request: web.Request) -> dict:
    """Middleware helper: extract and validate session from request cookie.

    Returns session dict on success.
    Raises web.HTTPUnauthorized (401) on missing, invalid, or expired session.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise web.HTTPUnauthorized(reason="No session cookie")

    session = await validate_session(token)
    if not session:
        raise web.HTTPUnauthorized(reason="Invalid or expired session")

    return session


async def handle_login(request: web.Request) -> web.Response:
    """POST /auth/login — validate DASHBOARD_SECRET, issue session cookie.

    Body: {"secret": "..."}
    Success: 200 + Set-Cookie header with session token
    Failure: 401 Unauthorized
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    provided = data.get("secret", "")
    try:
        expected = _get_dashboard_secret()
    except RuntimeError as exc:
        log.error("dashboard_secret_not_configured", exc=str(exc))
        return web.json_response({"error": "server configuration error"}, status=500)

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(provided.encode(), expected.encode()):
        log.warning("dashboard_login_failed")
        return web.json_response({"error": "Invalid credentials"}, status=401)

    user_id = await _get_owner_user_id()
    if user_id is None:
        log.error("dashboard_login_no_owner_record")
        return web.json_response(
            {"error": "Owner user record not found. Ensure Telegram bot has started once."},
            status=500,
        )

    try:
        token = await create_session(user_id)
    except RuntimeError as exc:
        log.error("dashboard_session_create_failed", exc=str(exc))
        return web.json_response({"error": "could not create session"}, status=500)

    response = web.json_response({"status": "ok", "message": "Logged in"})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=False,  # Caddy terminates TLS; internal traffic is HTTP
        samesite="Strict",
        max_age=SESSION_EXPIRY_DAYS * 86400,
        path="/",
    )
    log.info("dashboard_login_success", user_id=str(user_id))
    return response


async def handle_logout(request: web.Request) -> web.Response:
    """POST /auth/logout — invalidate session and clear cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await invalidate_session(token)

    response = web.json_response({"status": "ok", "message": "Logged out"})
    response.del_cookie(SESSION_COOKIE, path="/")
    return response
