"""Test for start_health_server — covers lines 267-287 in health.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_start_health_server_creates_runner():
    """start_health_server builds and starts the aiohttp app."""
    from orchestrator.health import start_health_server

    mock_runner = AsyncMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()

    mock_site = AsyncMock()
    mock_site.start = AsyncMock()

    with (
        patch("orchestrator.health.web.AppRunner", return_value=mock_runner),
        patch("orchestrator.health.web.TCPSite", return_value=mock_site),
    ):
        runner = await start_health_server(host="127.0.0.1", port=9999)

    assert runner is mock_runner
    mock_runner.setup.assert_called_once()
    mock_site.start.assert_called_once()
