"""Additional tests for telegram auth.py — covering remaining paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_auth_state():
    import clive_telegram.auth as auth_module
    old_pool = auth_module._pool
    old_allowed = frozenset(auth_module._allowed_chat_ids)
    auth_module._pool = None
    auth_module._allowed_chat_ids = set()
    yield
    auth_module._pool = old_pool
    auth_module._allowed_chat_ids = set(old_allowed)


# ---------------------------------------------------------------------------
# get_owner_chat_id
# ---------------------------------------------------------------------------

def test_get_owner_chat_id_returns_int():
    from clive_telegram.auth import get_owner_chat_id

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "12345"}):
        cid = get_owner_chat_id()

    assert cid == 12345
    assert isinstance(cid, int)


def test_get_owner_chat_id_raises_when_not_set():
    from clive_telegram.auth import get_owner_chat_id
    import os
    os.environ.pop("TELEGRAM_OWNER_CHAT_ID", None)

    with pytest.raises(RuntimeError, match="TELEGRAM_OWNER_CHAT_ID not set"):
        get_owner_chat_id()


# ---------------------------------------------------------------------------
# make_auth_metadata
# ---------------------------------------------------------------------------

def test_make_auth_metadata_returns_correct_structure():
    from clive_telegram.auth import make_auth_metadata

    metadata = make_auth_metadata(12345)

    assert metadata["surface_type"] == "telegram"
    assert metadata["surface_authenticated"] is True
    assert metadata["channel_id"] == "12345"


# ---------------------------------------------------------------------------
# refresh_auth_cache — pool is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_auth_cache_uses_env_var_when_pool_none():
    import clive_telegram.auth as auth_module

    auth_module._pool = None

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "99999"}):
        await auth_module.refresh_auth_cache()

    assert 99999 in auth_module._allowed_chat_ids


# ---------------------------------------------------------------------------
# register_owner_if_absent — when pool is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_owner_if_absent_skips_when_pool_none():
    import clive_telegram.auth as auth_module

    auth_module._pool = None

    # Should not raise; just logs warning
    await auth_module.register_owner_if_absent()


@pytest.mark.asyncio
async def test_register_owner_if_absent_upserts_when_pool_ready():
    import clive_telegram.auth as auth_module

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    auth_module._pool = mock_pool

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "12345"}):
        await auth_module.register_owner_if_absent()

    mock_conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# refresh_auth_cache — existing cache preserved on db error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_auth_cache_keeps_existing_on_error_when_cache_not_empty():
    import clive_telegram.auth as auth_module

    # Pre-populate cache
    auth_module._allowed_chat_ids = {12345}

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=Exception("connection refused"))
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    auth_module._pool = mock_pool

    with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "12345"}):
        await auth_module.refresh_auth_cache()

    # Cache should NOT have been replaced with fallback since it was non-empty
    # (behaviour: only falls back to env var if cache IS empty after error)
    assert 12345 in auth_module._allowed_chat_ids
