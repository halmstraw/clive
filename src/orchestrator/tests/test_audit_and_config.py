"""Tests for orchestrator audit.py and config_handler.py."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent, AlignmentResult


# ---------------------------------------------------------------------------
# audit.py
# ---------------------------------------------------------------------------

class TestAuditWrite:
    @pytest.mark.asyncio
    async def test_write_calls_db_execute(self):
        from orchestrator import audit

        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={"input_text": "hello"},
            conversation_id=uuid.uuid4(),
        )

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = audit._pool
        try:
            audit._pool = mock_pool
            with patch.object(audit, "audit_writes_total") as mock_counter:
                mock_counter.inc = MagicMock()
                await audit.write(event, AlignmentResult.PASS, "routed")
            mock_conn.execute.assert_called_once()
            mock_counter.inc.assert_called_once()
        finally:
            audit._pool = original_pool

    @pytest.mark.asyncio
    async def test_write_raises_when_pool_not_init(self):
        from orchestrator import audit

        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={},
        )

        original_pool = audit._pool
        try:
            audit._pool = None
            with pytest.raises(RuntimeError, match="Audit pool not initialised"):
                await audit.write(event, AlignmentResult.PASS, "routed")
        finally:
            audit._pool = original_pool


# ---------------------------------------------------------------------------
# config_handler.py
# ---------------------------------------------------------------------------

class TestConfigHandlerSetSpendCap:
    @pytest.mark.asyncio
    async def test_upserts_spend_cap(self):
        from orchestrator import config_handler
        from orchestrator.events.schema import CLIVEEvent

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "config.set_spend_cap", "action_target": "5.0"},
        )

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # no existing cap
        mock_conn.execute = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = config_handler._pool
        try:
            config_handler._pool = mock_pool
            # The bus is imported locally inside handle_config_set_spend_cap;
            # patch the singleton on the orchestrator.bus module directly.
            with patch("orchestrator.bus.bus") as mock_bus:
                mock_bus.publish = AsyncMock()
                await config_handler.handle_config_set_spend_cap(event)
            # Should have called fetchrow and execute
            mock_conn.fetchrow.assert_called()
            mock_conn.execute.assert_called()
        finally:
            config_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_invalid_cap_value_is_logged_and_returns(self):
        from orchestrator import config_handler
        from orchestrator.events.schema import CLIVEEvent

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "config.set_spend_cap", "action_target": "not-a-number"},
        )

        # Should not raise; should just log and return
        original_pool = config_handler._pool
        try:
            config_handler._pool = MagicMock()
            await config_handler.handle_config_set_spend_cap(event)
        finally:
            config_handler._pool = original_pool


class TestConfigHandlerWorkerReschedule:
    @pytest.mark.asyncio
    async def test_reschedules_worker(self):
        from orchestrator import config_handler
        from orchestrator.events.schema import CLIVEEvent

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={
                "action_type": "worker.reschedule",
                "action_target": "daily_digest:0 10 * * *",
            },
        )

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"cron_expression": "0 8 * * *"})
        mock_conn.execute = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="daily_digest")
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = config_handler._pool
        try:
            config_handler._pool = mock_pool
            with patch("orchestrator.bus.bus") as mock_bus:
                mock_bus.publish = AsyncMock()
                await config_handler.handle_worker_reschedule(event)
            mock_conn.fetchrow.assert_called()
        finally:
            config_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_missing_colon_logs_and_returns(self):
        from orchestrator import config_handler
        from orchestrator.events.schema import CLIVEEvent

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "worker.reschedule", "action_target": "no-colon-here"},
        )

        # Should not raise
        original_pool = config_handler._pool
        try:
            config_handler._pool = MagicMock()
            await config_handler.handle_worker_reschedule(event)
        finally:
            config_handler._pool = original_pool

    @pytest.mark.asyncio
    async def test_worker_not_found_logs_and_returns(self):
        from orchestrator import config_handler
        from orchestrator.events.schema import CLIVEEvent

        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=9,
            payload={"action_type": "worker.reschedule", "action_target": "nonexistent:0 10 * * *"},
        )

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # worker not found
        mock_conn.execute = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        original_pool = config_handler._pool
        try:
            config_handler._pool = mock_pool
            # Should not raise
            await config_handler.handle_worker_reschedule(event)
        finally:
            config_handler._pool = original_pool

    def test_get_pool_raises_when_not_init(self):
        from orchestrator import config_handler

        original_pool = config_handler._pool
        try:
            config_handler._pool = None
            with pytest.raises(RuntimeError):
                config_handler._get_pool()
        finally:
            config_handler._pool = original_pool
