"""Tests for telegram main.py startup flow — covering lines 213-323."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_main_startup_and_shutdown():
    """Test the main() function startup + immediate signal stop."""
    from clive_telegram import main as main_mod

    # Mock all external dependencies
    mock_db = AsyncMock()
    mock_auth = MagicMock()
    mock_auth.init_pool = AsyncMock()
    mock_auth.register_owner_if_absent = AsyncMock()
    mock_auth.refresh_auth_cache = AsyncMock()
    mock_auth.auth_cache_refresh_loop = AsyncMock()

    # Mock the Application builder chain
    mock_updater = AsyncMock()
    mock_updater.start_polling = AsyncMock()
    mock_updater.stop = AsyncMock()

    mock_application = AsyncMock()
    mock_application.add_handler = MagicMock()
    mock_application.initialize = AsyncMock()
    mock_application.start = AsyncMock()
    mock_application.stop = AsyncMock()
    mock_application.shutdown = AsyncMock()
    mock_application.updater = mock_updater

    mock_builder = MagicMock()
    mock_builder.token = MagicMock(return_value=mock_builder)
    mock_builder.build = MagicMock(return_value=mock_application)

    # Mock aiohttp
    mock_runner = AsyncMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()

    mock_site = AsyncMock()
    mock_site.start = AsyncMock()

    # Create a stop event that we'll set immediately to exit the wait loop
    real_stop_event = asyncio.Event()
    real_stop_event.set()  # Immediately "stopped"

    with (
        patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_OWNER_CHAT_ID": "12345",
            "APP_DB_PASSWORD": "testpass",
        }),
        patch("clive_telegram.main.db.init_pool", AsyncMock()),
        patch("clive_telegram.main.auth", mock_auth),
        patch("clive_telegram.main.Application") as mock_app_class,
        patch("clive_telegram.main.web.Application", return_value=MagicMock(
            router=MagicMock(
                add_post=MagicMock(),
                add_get=MagicMock(),
            )
        )),
        patch("clive_telegram.main.web.AppRunner", return_value=mock_runner),
        patch("clive_telegram.main.web.TCPSite", return_value=mock_site),
        patch("clive_telegram.main.asyncio.Event", return_value=real_stop_event),
        patch("clive_telegram.main.asyncio.get_running_loop", return_value=MagicMock(
            add_signal_handler=MagicMock()
        )),
    ):
        mock_app_class.builder = MagicMock(return_value=mock_builder)
        await main_mod.main()

    # Verify startup sequence was called
    mock_auth.init_pool.assert_called_once()
    mock_auth.register_owner_if_absent.assert_called_once()
    mock_auth.refresh_auth_cache.assert_called_once()
    mock_application.initialize.assert_called_once()
    mock_application.start.assert_called_once()
    mock_updater.start_polling.assert_called_once()
    mock_runner.cleanup.assert_called_once()
