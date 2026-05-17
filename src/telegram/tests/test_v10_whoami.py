"""Tests for v0.10 /whoami command handler (bot.py).

D-144 acceptance criteria:
  - /whoami returns profile text (Chat ID, role, zone_access, member since) when user found
  - /whoami returns "not yet registered" message when get_user_profile returns None
  - Unauthenticated callers are silently ignored (D-057)

D-001: /whoami is owner-only — gated by is_authenticated.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


CHAT_ID = 12345


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(chat_id: int = CHAT_ID) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_context() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# /whoami — profile found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_returns_profile_text_when_user_found():
    """Profile returned by get_user_profile → reply contains role, zone, date."""
    from clive_telegram.bot import whoami_command

    profile = {
        "telegram_chat_id": CHAT_ID,
        "role": "owner",
        "zone_access": ["personal"],
        "created_at": "2026-05-17T12:00:00+00:00",
    }

    update = _make_update()
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.auth") as mock_auth:
        mock_auth.get_user_profile = AsyncMock(return_value=profile)
        await whoami_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "owner" in call_text
    assert "personal" in call_text
    assert "2026-05-17" in call_text


@pytest.mark.asyncio
async def test_whoami_includes_chat_id_in_profile():
    """Reply text includes the caller's chat ID."""
    from clive_telegram.bot import whoami_command

    profile = {
        "telegram_chat_id": CHAT_ID,
        "role": "owner",
        "zone_access": ["personal"],
        "created_at": "2026-05-17T08:00:00+00:00",
    }

    update = _make_update()
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.auth") as mock_auth:
        mock_auth.get_user_profile = AsyncMock(return_value=profile)
        await whoami_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert str(CHAT_ID) in call_text


# ---------------------------------------------------------------------------
# /whoami — profile not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_returns_not_registered_when_profile_is_none():
    """get_user_profile returns None → "not yet registered" message."""
    from clive_telegram.bot import whoami_command

    update = _make_update()
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=True), \
         patch("clive_telegram.bot.auth") as mock_auth:
        mock_auth.get_user_profile = AsyncMock(return_value=None)
        await whoami_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "not yet registered" in call_text


# ---------------------------------------------------------------------------
# /whoami — authentication guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_ignores_unauthenticated_caller():
    """Unauthenticated callers get no reply — D-057."""
    from clive_telegram.bot import whoami_command

    update = _make_update()
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=False):
        await whoami_command(update, context)

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_whoami_does_not_call_get_user_profile_when_unauthenticated():
    """get_user_profile must not be called for unauthenticated requests."""
    from clive_telegram.bot import whoami_command

    update = _make_update()
    context = _make_context()

    with patch("clive_telegram.bot.is_authenticated", return_value=False), \
         patch("clive_telegram.bot.auth") as mock_auth:
        mock_auth.get_user_profile = AsyncMock()
        await whoami_command(update, context)

    mock_auth.get_user_profile.assert_not_called()
