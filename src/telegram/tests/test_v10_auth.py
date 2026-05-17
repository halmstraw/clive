"""Tests for v0.10 DB-backed authentication (auth.py).

D-143/D-144 acceptance criteria:
  - is_authenticated uses DB-backed cache; falls back to env-var when cache empty
  - refresh_auth_cache populates _allowed_chat_ids from clive_state.users
  - get_user_profile returns populated dict or None
  - get_user_profile returns None when pool not initialised

D-057: channel membership is the authentication factor — preserved through the
DB-backed upgrade. The model changes (DB source), the factor does not.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


OWNER_CHAT_ID = 12345
OTHER_CHAT_ID = 99999


# ---------------------------------------------------------------------------
# Fixtures — reset module-level auth state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_auth_state():
    """Snapshot and restore module-level auth state around each test."""
    import clive_telegram.auth as auth_module

    old_pool = auth_module._pool
    old_allowed = frozenset(auth_module._allowed_chat_ids)
    auth_module._pool = None
    auth_module._allowed_chat_ids = set()
    yield
    auth_module._pool = old_pool
    auth_module._allowed_chat_ids = set(old_allowed)


# ---------------------------------------------------------------------------
# is_authenticated — cache-backed behaviour
# ---------------------------------------------------------------------------

def test_is_authenticated_returns_true_when_in_cache():
    """chat_id present in _allowed_chat_ids → authenticated."""
    import clive_telegram.auth as auth_module

    auth_module._allowed_chat_ids = {OWNER_CHAT_ID}

    assert auth_module.is_authenticated(OWNER_CHAT_ID) is True


def test_is_authenticated_returns_false_when_not_in_cache():
    """chat_id absent from _allowed_chat_ids → not authenticated."""
    import clive_telegram.auth as auth_module

    auth_module._allowed_chat_ids = {OWNER_CHAT_ID}

    assert auth_module.is_authenticated(OTHER_CHAT_ID) is False


def test_is_authenticated_falls_back_to_env_var_when_cache_empty():
    """Empty cache → fall back to env-var comparison (D-057 preserved)."""
    import clive_telegram.auth as auth_module

    auth_module._allowed_chat_ids = set()

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": str(OWNER_CHAT_ID)}):
        assert auth_module.is_authenticated(OWNER_CHAT_ID) is True
        assert auth_module.is_authenticated(OTHER_CHAT_ID) is False


# ---------------------------------------------------------------------------
# refresh_auth_cache — DB population
# ---------------------------------------------------------------------------

def _make_pool_with_fetch(rows: list[dict]) -> MagicMock:
    """Build a minimal mock asyncpg pool that returns rows from conn.fetch()."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=rows)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


@pytest.mark.asyncio
async def test_refresh_auth_cache_populates_from_db():
    """refresh_auth_cache loads telegram_chat_ids from DB rows."""
    import clive_telegram.auth as auth_module

    auth_module._pool = _make_pool_with_fetch([
        {"telegram_chat_id": OWNER_CHAT_ID},
        {"telegram_chat_id": 22222},
    ])

    await auth_module.refresh_auth_cache()

    assert OWNER_CHAT_ID in auth_module._allowed_chat_ids
    assert 22222 in auth_module._allowed_chat_ids


@pytest.mark.asyncio
async def test_refresh_auth_cache_falls_back_to_env_var_when_db_returns_empty():
    """Empty DB result → fallback to env-var so bot stays responsive."""
    import clive_telegram.auth as auth_module

    auth_module._pool = _make_pool_with_fetch([])

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": str(OWNER_CHAT_ID)}):
        await auth_module.refresh_auth_cache()

    assert OWNER_CHAT_ID in auth_module._allowed_chat_ids


@pytest.mark.asyncio
async def test_refresh_auth_cache_falls_back_to_env_var_on_db_error():
    """DB error → fallback to env-var; bot stays responsive (fail-open)."""
    import clive_telegram.auth as auth_module

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=Exception("connection refused"))
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    auth_module._pool = mock_pool

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": str(OWNER_CHAT_ID)}):
        await auth_module.refresh_auth_cache()

    assert OWNER_CHAT_ID in auth_module._allowed_chat_ids


# ---------------------------------------------------------------------------
# get_user_profile
# ---------------------------------------------------------------------------

def _make_pool_with_fetchrow(row) -> MagicMock:
    """Build a minimal mock asyncpg pool that returns row from conn.fetchrow()."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=row)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


@pytest.mark.asyncio
async def test_get_user_profile_returns_dict_for_known_chat_id():
    """Known chat_id → dict with correct user_id, role, zone_access, created_at."""
    import clive_telegram.auth as auth_module

    fake_user_id = uuid.uuid4()
    fake_created_at = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)

    mock_row = {
        "user_id": fake_user_id,
        "telegram_chat_id": OWNER_CHAT_ID,
        "role": "owner",
        "zone_access": ["personal"],
        "created_at": fake_created_at,
    }
    auth_module._pool = _make_pool_with_fetchrow(mock_row)

    result = await auth_module.get_user_profile(OWNER_CHAT_ID)

    assert result is not None
    assert result["user_id"] == str(fake_user_id)
    assert result["telegram_chat_id"] == OWNER_CHAT_ID
    assert result["role"] == "owner"
    assert result["zone_access"] == ["personal"]
    assert result["created_at"].startswith("2026-05-17")


@pytest.mark.asyncio
async def test_get_user_profile_returns_none_for_unknown_chat_id():
    """Unknown chat_id → fetchrow returns None → get_user_profile returns None."""
    import clive_telegram.auth as auth_module

    auth_module._pool = _make_pool_with_fetchrow(None)

    result = await auth_module.get_user_profile(OTHER_CHAT_ID)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_profile_returns_none_when_pool_not_initialised():
    """Pool is None (pre-startup or DB unavailable) → None returned, no crash."""
    import clive_telegram.auth as auth_module

    auth_module._pool = None

    result = await auth_module.get_user_profile(OWNER_CHAT_ID)

    assert result is None
