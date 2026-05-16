"""v0.8 Block 17 — Unit tests for the tool registry gate and admin handlers.

Criteria covered (DONE WHEN from task spec):
  Gate: rejection for unregistered tool
  Gate: rejection for disabled tool
  Gate: rejection for deprecated tool (spec requirement, beyond DONE WHEN minimum)
  Gate: successful dispatch when tool is registered, enabled, and not deprecated
  Admin: successful disable — emits admin.tool_updated { action: "disabled" }
  Admin: tool_not_found on disable — emits admin.tool_error { reason: "tool_not_found" }
  Admin: successful enable — emits admin.tool_updated { action: "enabled" }
  Admin: tool_not_found on enable — emits admin.tool_error { reason: "tool_not_found" }
  Admin: not-confirmed disable is silently ignored (D-006 trust flag guard)
  Admin: not-confirmed enable is silently ignored (D-006 trust flag guard)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent
from orchestrator.events.taxonomy import (
    ACTION_PENDING,
    ACTION_REJECTED,
    ADMIN_TOOL_DISABLE,
    ADMIN_TOOL_ENABLE,
    ADMIN_TOOL_ERROR,
    ADMIN_TOOL_UPDATED,
)
from orchestrator.registry import (
    handle_tool_disable,
    handle_tool_enable,
    make_gated_handler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action_pending_event(action_type: str = "web.search") -> CLIVEEvent:
    return CLIVEEvent(
        event_type=ACTION_PENDING,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload={
            "action_type": action_type,
            "action_target": "test query",
            "action_description": "Test action",
            "chat_id": 12345,
        },
    )


def _make_admin_event(
    event_type: str,
    tool_name: str,
    confirmed: bool = True,
) -> CLIVEEvent:
    return CLIVEEvent(
        event_type=event_type,
        source_block=23,
        conversation_id=uuid.uuid4(),
        payload={"tool_name": tool_name, "confirmed": confirmed},
    )


def _make_mock_pool(
    fetchrow_return=None,
    execute_return: str = "UPDATE 1",
):
    """Create a mock asyncpg pool with configurable fetchrow and execute returns."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock(return_value=execute_return)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


# ---------------------------------------------------------------------------
# Registry gate tests
# ---------------------------------------------------------------------------

class TestRegistryGate:

    @pytest.mark.asyncio
    async def test_unregistered_tool_emits_action_rejected(self):
        """action.pending for a tool not in the registry must emit action.rejected
        with reason='tool_not_registered'. Block 9 handler must not be called."""
        pool, _ = _make_mock_pool(fetchrow_return=None)
        event = _make_action_pending_event("web.search")
        emitted: list[CLIVEEvent] = []
        original_handler = AsyncMock()

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        gated = make_gated_handler(original_handler)

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        original_handler.assert_not_called()
        assert len(emitted) == 1
        assert emitted[0].event_type == ACTION_REJECTED
        assert emitted[0].payload["tool_name"] == "web_search"
        assert emitted[0].payload["reason"] == "tool_not_registered"
        assert emitted[0].payload["original_event_id"] == str(event.event_id)

    @pytest.mark.asyncio
    async def test_disabled_tool_emits_action_rejected(self):
        """action.pending for a disabled tool must emit action.rejected
        with reason='tool_disabled'. Block 9 handler must not be called."""
        pool, _ = _make_mock_pool(fetchrow_return={"enabled": False, "deprecated": False})
        event = _make_action_pending_event("reminder.schedule")
        emitted: list[CLIVEEvent] = []
        original_handler = AsyncMock()

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        gated = make_gated_handler(original_handler)

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        original_handler.assert_not_called()
        assert len(emitted) == 1
        assert emitted[0].event_type == ACTION_REJECTED
        assert emitted[0].payload["tool_name"] == "reminder"
        assert emitted[0].payload["reason"] == "tool_disabled"
        assert emitted[0].payload["original_event_id"] == str(event.event_id)

    @pytest.mark.asyncio
    async def test_deprecated_tool_emits_action_rejected(self):
        """action.pending for a deprecated tool must emit action.rejected
        with reason='tool_deprecated'. Block 9 handler must not be called."""
        pool, _ = _make_mock_pool(fetchrow_return={"enabled": True, "deprecated": True})
        event = _make_action_pending_event("document.delete")
        emitted: list[CLIVEEvent] = []
        original_handler = AsyncMock()

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        gated = make_gated_handler(original_handler)

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        original_handler.assert_not_called()
        assert len(emitted) == 1
        assert emitted[0].event_type == ACTION_REJECTED
        assert emitted[0].payload["tool_name"] == "delete_document"
        assert emitted[0].payload["reason"] == "tool_deprecated"
        assert emitted[0].payload["original_event_id"] == str(event.event_id)

    @pytest.mark.asyncio
    async def test_enabled_non_deprecated_tool_dispatches_to_handler(self):
        """action.pending for an enabled, non-deprecated tool must call the
        original Block 9 handler. No action.rejected must be emitted."""
        pool, _ = _make_mock_pool(fetchrow_return={"enabled": True, "deprecated": False})
        event = _make_action_pending_event("web.search")
        emitted: list[CLIVEEvent] = []
        original_handler = AsyncMock()

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        gated = make_gated_handler(original_handler)

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        original_handler.assert_called_once_with(event)
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_rejection_source_block_is_13(self):
        """Registry rejections must identify Block 13 as the source."""
        pool, _ = _make_mock_pool(fetchrow_return=None)
        event = _make_action_pending_event("web.search")
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        gated = make_gated_handler(AsyncMock())

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        assert emitted[0].source_block == 13

    @pytest.mark.asyncio
    async def test_gate_queries_correct_tool_name_for_web_search(self):
        """Gate must query 'web_search' (not 'web.search') for action_type='web.search'."""
        pool, conn = _make_mock_pool(fetchrow_return={"enabled": True, "deprecated": False})
        event = _make_action_pending_event("web.search")

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()

        gated = make_gated_handler(AsyncMock())

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await gated(event)

        # Verify the DB was queried with the registry tool_name, not the action_type
        conn.fetchrow.assert_called_once()
        call_args = conn.fetchrow.call_args
        sql, tool_name_arg = call_args.args[0], call_args.args[1]
        assert "tool_registry" in sql
        assert tool_name_arg == "web_search"


# ---------------------------------------------------------------------------
# Admin tool disable tests
# ---------------------------------------------------------------------------

class TestAdminToolDisable:

    @pytest.mark.asyncio
    async def test_disable_success_emits_tool_updated(self):
        """admin.tool_disable with confirmed=True and an existing tool must
        UPDATE enabled=FALSE and emit admin.tool_updated with action='disabled'."""
        pool, conn = _make_mock_pool(execute_return="UPDATE 1")
        event = _make_admin_event(ADMIN_TOOL_DISABLE, "web_search", confirmed=True)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_disable(event)

        # Verify DB update was called
        conn.execute.assert_called_once()
        sql = conn.execute.call_args.args[0]
        assert "tool_registry" in sql
        assert "enabled" in sql

        # Verify emitted event
        assert len(emitted) == 1
        assert emitted[0].event_type == ADMIN_TOOL_UPDATED
        assert emitted[0].payload["tool_name"] == "web_search"
        assert emitted[0].payload["action"] == "disabled"

    @pytest.mark.asyncio
    async def test_disable_tool_not_found_emits_tool_error(self):
        """admin.tool_disable for a tool_name not in the registry must emit
        admin.tool_error with reason='tool_not_found'."""
        pool, _ = _make_mock_pool(execute_return="UPDATE 0")
        event = _make_admin_event(ADMIN_TOOL_DISABLE, "nonexistent_tool", confirmed=True)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_disable(event)

        assert len(emitted) == 1
        assert emitted[0].event_type == ADMIN_TOOL_ERROR
        assert emitted[0].payload["tool_name"] == "nonexistent_tool"
        assert emitted[0].payload["reason"] == "tool_not_found"

    @pytest.mark.asyncio
    async def test_disable_not_confirmed_is_ignored(self):
        """D-006: admin.tool_disable without confirmed=True must be silently
        ignored — no DB update, no event emitted."""
        pool, conn = _make_mock_pool()
        event = _make_admin_event(ADMIN_TOOL_DISABLE, "web_search", confirmed=False)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_disable(event)

        conn.execute.assert_not_called()
        assert len(emitted) == 0


# ---------------------------------------------------------------------------
# Admin tool enable tests
# ---------------------------------------------------------------------------

class TestAdminToolEnable:

    @pytest.mark.asyncio
    async def test_enable_success_emits_tool_updated(self):
        """admin.tool_enable with confirmed=True and an existing tool must
        UPDATE enabled=TRUE and emit admin.tool_updated with action='enabled'."""
        pool, conn = _make_mock_pool(execute_return="UPDATE 1")
        event = _make_admin_event(ADMIN_TOOL_ENABLE, "web_search", confirmed=True)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_enable(event)

        # Verify DB update was called
        conn.execute.assert_called_once()
        sql = conn.execute.call_args.args[0]
        assert "tool_registry" in sql
        assert "enabled" in sql

        # Verify emitted event
        assert len(emitted) == 1
        assert emitted[0].event_type == ADMIN_TOOL_UPDATED
        assert emitted[0].payload["tool_name"] == "web_search"
        assert emitted[0].payload["action"] == "enabled"

    @pytest.mark.asyncio
    async def test_enable_tool_not_found_emits_tool_error(self):
        """admin.tool_enable for a tool_name not in the registry must emit
        admin.tool_error with reason='tool_not_found'."""
        pool, _ = _make_mock_pool(execute_return="UPDATE 0")
        event = _make_admin_event(ADMIN_TOOL_ENABLE, "nonexistent_tool", confirmed=True)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_enable(event)

        assert len(emitted) == 1
        assert emitted[0].event_type == ADMIN_TOOL_ERROR
        assert emitted[0].payload["tool_name"] == "nonexistent_tool"
        assert emitted[0].payload["reason"] == "tool_not_found"

    @pytest.mark.asyncio
    async def test_enable_not_confirmed_is_ignored(self):
        """D-006: admin.tool_enable without confirmed=True must be silently
        ignored — no DB update, no event emitted."""
        pool, conn = _make_mock_pool()
        event = _make_admin_event(ADMIN_TOOL_ENABLE, "web_search", confirmed=False)
        emitted: list[CLIVEEvent] = []

        import orchestrator.bus as bus_module
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=lambda e: emitted.append(e))

        with (
            patch("orchestrator.registry._pool", pool),
            patch("orchestrator.audit.write", new_callable=AsyncMock),
            patch.object(bus_module, "bus", mock_bus),
        ):
            await handle_tool_enable(event)

        conn.execute.assert_not_called()
        assert len(emitted) == 0
