"""Channel-as-authentication for Block 23.

D-057: the Telegram channel is the authentication factor.
D-058: Block 23 attaches surface authentication metadata to
       inbound events before they reach Block 13.

At v0.1, authentication is: is the message from the owner's
Telegram chat ID? The owner's chat ID is set as an environment
variable at deploy time. Any message not from this chat ID is
silently ignored.

v0.10 (D-143/D-144): DB-backed auth cache populated from
clive_state.users at startup, refreshed every 60 seconds.
Falls back to env-var check if cache is empty or DB unreachable.
Owner record upserted from TELEGRAM_OWNER_CHAT_ID at startup.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None
_allowed_chat_ids: set[int] = set()
_AUTH_CACHE_REFRESH_SECONDS = 60


def get_owner_chat_id() -> int:
    """Return the owner's Telegram chat ID from environment."""
    raw = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not raw:
        raise RuntimeError("TELEGRAM_OWNER_CHAT_ID not set")
    return int(raw)


async def init_pool() -> None:
    """Initialise auth DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    log.info("auth_pool_initialised")


async def register_owner_if_absent() -> None:
    """Upsert owner record from TELEGRAM_OWNER_CHAT_ID env var.

    D-144: owner is registered by Block 23 at startup.
    Uses INSERT ... ON CONFLICT DO NOTHING to be idempotent.
    If pool not ready: log WARNING and skip (non-fatal).
    """
    if _pool is None:
        log.warning("auth_pool_not_ready_for_owner_registration")
        return
    owner_chat_id = get_owner_chat_id()
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clive_state.users
              (telegram_chat_id, role, zone_access)
            VALUES ($1, 'owner', ARRAY['personal'])
            ON CONFLICT (telegram_chat_id) DO NOTHING
            """,
            owner_chat_id,
        )
    log.info("owner_registration_checked", chat_id=owner_chat_id)


async def refresh_auth_cache() -> None:
    """Load allowed telegram_chat_ids from users table into _allowed_chat_ids.

    Runs at startup and every _AUTH_CACHE_REFRESH_SECONDS seconds.
    Falls back to env var if pool is not ready.
    """
    global _allowed_chat_ids
    if _pool is None:
        _allowed_chat_ids = {get_owner_chat_id()}
        return
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT telegram_chat_id FROM clive_state.users"
            )
        _allowed_chat_ids = {row["telegram_chat_id"] for row in rows}
        if not _allowed_chat_ids:
            # Bootstrap: no users yet — fall back to env var
            _allowed_chat_ids = {get_owner_chat_id()}
            log.warning("auth_cache_empty_using_env_var_fallback")
    except Exception as exc:  # noqa: BLE001
        log.warning("auth_cache_refresh_error", exc=str(exc))
        if not _allowed_chat_ids:
            _allowed_chat_ids = {get_owner_chat_id()}


async def auth_cache_refresh_loop() -> None:
    """Background coroutine: refresh auth cache every 60 seconds."""
    while True:
        try:
            await asyncio.sleep(_AUTH_CACHE_REFRESH_SECONDS)
            await refresh_auth_cache()
        except asyncio.CancelledError:
            return


def is_authenticated(chat_id: int) -> bool:
    """Return True if chat_id is in the allowed set.

    Cache is populated from clive_state.users at startup and refreshed
    every 60 seconds. Falls back to env-var check if cache is empty.
    D-057: channel membership is the authentication factor.
    D-001: single owner — one chat ID is the complete auth model at v0.1.
    """
    if _allowed_chat_ids:
        authenticated = chat_id in _allowed_chat_ids
    else:
        authenticated = chat_id == get_owner_chat_id()
    if not authenticated:
        log.warning("unauthenticated_message", chat_id=chat_id)
    return authenticated


async def get_user_profile(chat_id: int) -> dict | None:
    """Return user record from clive_state.users for this chat_id, or None.

    Used by /whoami (D-144) to display the owner's profile.
    Returns None if pool is not initialised or user not found.
    """
    if _pool is None:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, telegram_chat_id, role, zone_access, created_at
            FROM clive_state.users
            WHERE telegram_chat_id = $1
            """,
            chat_id,
        )
    if not row:
        return None
    return {
        "user_id": str(row["user_id"]),
        "telegram_chat_id": row["telegram_chat_id"],
        "role": row["role"],
        "zone_access": list(row["zone_access"]),
        "created_at": row["created_at"].isoformat(),
    }


def make_auth_metadata(chat_id: int) -> dict:
    """Build surface authentication metadata attached to outbound events.

    D-058: Block 23 attaches this; Block 13 enforces it.
    """
    return {
        "surface_type": "telegram",
        "surface_authenticated": True,
        "channel_id": str(chat_id),
    }
