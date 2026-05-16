"""Tests for v0.8 tool management commands: /tools, /tool_disable, /tool_enable.

D-138 acceptance criteria covered:
  Criterion 2: /tools lists all registered tools with correct formatting
  Criterion 3: /tools returns empty message when no tools registered
  Criterion 4: Block 13 rejects actions for disabled tools (verified via
               admin.tool_disable event emission from Block 23)
  Criterion 5: /tool_disable and /tool_enable route through confirmation gate
               — D-006 satisfied

Additional coverage:
  - /tool_disable not-found case
  - /tool_disable already-disabled case
  - /tool_disable no-args usage hint
  - /tool_enable not-found case
  - /tool_enable already-enabled case (plain and with deprecation note)
  - /tool_enable deprecated-tool confirmation prompt variant
  - /confirm_action with tool op pending → emits admin.tool_disable / admin.tool_enable
  - /cancel_action with tool op pending → replies cancelled message
  - deliver_tool_updated → sends correct success text (disable / enable / enable+deprecated)
  - deliver_tool_error → sends registry-unavailable message
  - Registry DB error → "Tool registry is unavailable." response

D-057: all command tests use is_authenticated=True / owner chat_id only.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

CHAT_ID = 88888


@pytest.fixture(autouse=True)
def reset_tool_state():
    """Clear tool management state between tests."""
    import clive_telegram.bot as bot_module

    bot_module._pending_tool_ops.clear()
    bot_module._confirmed_tool_ops.clear()
    yield
    bot_module._pending_tool_ops.clear()
    bot_module._confirmed_tool_ops.clear()


def _make_update(chat_id: int = CHAT_ID, args_text: str = "") -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_context(args: list[str] | None = None) -> MagicMock:
    context = MagicMock()
    context.args = args or []
    return context


_UNSET = object()  # sentinel for _make_pool kwargs


def _make_pool(fetchrow_result=_UNSET, fetch_result=_UNSET, raise_exc=None):
    """Build a mock asyncpg pool for tool_registry reads.

    Use fetchrow_result=None explicitly to simulate a not-found result.
    Omit the argument (or use _UNSET) to leave the mock unconfigured.
    """
    pool = MagicMock()
    conn = AsyncMock()

    if raise_exc is not None:
        conn.fetchrow = AsyncMock(side_effect=raise_exc)
        conn.fetch = AsyncMock(side_effect=raise_exc)
    else:
        if fetchrow_result is not _UNSET:
            conn.fetchrow = AsyncMock(return_value=fetchrow_result)
        if fetch_result is not _UNSET:
            conn.fetch = AsyncMock(return_value=fetch_result)

    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acm)
    return pool


def _tool_row(
    tool_name: str = "web_search",
    display_name: str = "Web Search",
    version: str = "1.0.0",
    description: str = "Searches the web for information",
    enabled: bool = True,
    deprecated: bool = False,
    deprecation_note: str | None = None,
    health_status: str = "healthy",
) -> dict:
    """Build a dict that mirrors an asyncpg tool_registry Record."""
    return {
        "tool_name": tool_name,
        "display_name": display_name,
        "version": version,
        "description": description,
        "enabled": enabled,
        "deprecated": deprecated,
        "deprecation_note": deprecation_note,
        "health_status": health_status,
    }


# ---------------------------------------------------------------------------
# _format_tool_entry helpers (unit tests for the formatting function)
# ---------------------------------------------------------------------------

class TestFormatToolEntry:
    def test_enabled_healthy_tool(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(tool_name="web_search", version="1.0.0", enabled=True)
        entry = _format_tool_entry(row)

        assert "`web_search` v1.0.0 — enabled" in entry
        assert "Web Search. Searches the web for information" in entry

    def test_disabled_tool(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(tool_name="reminder", enabled=False)
        entry = _format_tool_entry(row)

        assert "disabled" in entry
        assert "enabled" not in entry.split("—")[1]  # status label after the dash

    def test_deprecated_tool_adds_suffix_and_note(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(
            tool_name="old_tool",
            enabled=True,
            deprecated=True,
            deprecation_note="use new_tool instead",
        )
        entry = _format_tool_entry(row)

        assert "enabled [deprecated]" in entry
        assert "Deprecated: use new_tool instead" in entry

    def test_deprecated_no_note_omits_third_line(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(enabled=True, deprecated=True, deprecation_note=None)
        entry = _format_tool_entry(row)

        assert "[deprecated]" in entry
        assert "Deprecated:" not in entry

    def test_unhealthy_tool_shows_health_status(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(enabled=True, health_status="degraded")
        entry = _format_tool_entry(row)

        assert "[health: degraded]" in entry

    def test_unavailable_tool_shows_health_status(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(enabled=True, health_status="unavailable")
        entry = _format_tool_entry(row)

        assert "[health: unavailable]" in entry

    def test_healthy_tool_no_health_suffix(self):
        from clive_telegram.bot import _format_tool_entry

        row = _tool_row(enabled=True, health_status="healthy")
        entry = _format_tool_entry(row)

        assert "[health:" not in entry


# ---------------------------------------------------------------------------
# /tools — D-138 criteria 2 & 3
# ---------------------------------------------------------------------------

class TestHandleTools:
    @pytest.mark.asyncio
    async def test_tools_empty_registry_replies_empty_message(self):
        """/tools with no rows returns the canonical empty message (UX spec 1.3)."""
        from clive_telegram.bot import handle_tools

        update = _make_update()
        context = _make_context()
        mock_pool = _make_pool(fetch_result=[])

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tools(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert text == "No tools are registered."

    @pytest.mark.asyncio
    async def test_tools_with_single_entry_formats_correctly(self):
        """/tools with one entry produces correct header and entry format (UX spec 1.2)."""
        from clive_telegram.bot import handle_tools

        rows = [
            _tool_row(
                tool_name="web_search",
                display_name="Web Search",
                version="1.0.0",
                description="Searches the web for current information",
                enabled=True,
            )
        ]
        update = _make_update()
        context = _make_context()
        mock_pool = _make_pool(fetch_result=rows)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tools(update, context)

        update.message.reply_text.assert_called_once()
        text, kwargs = (
            update.message.reply_text.call_args[0][0],
            update.message.reply_text.call_args[1],
        )
        assert "Tools — 1 registered" in text
        assert "`web_search` v1.0.0 — enabled" in text
        assert "Web Search. Searches the web for current information" in text
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_tools_with_multiple_entries_shows_count(self):
        """/tools with three entries shows count N=3 in header."""
        from clive_telegram.bot import handle_tools

        rows = [
            _tool_row("reminder", "Reminder", enabled=True),
            _tool_row("tool_b", "Tool B", enabled=False),
            _tool_row("web_search", "Web Search", enabled=True),
        ]
        update = _make_update()
        context = _make_context()
        mock_pool = _make_pool(fetch_result=rows)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tools(update, context)

        # All three entries should appear (may be one or more messages)
        all_text = " ".join(
            str(call[0][0]) for call in update.message.reply_text.call_args_list
        )
        assert "Tools — 3 registered" in all_text

    @pytest.mark.asyncio
    async def test_tools_deprecated_entry_includes_note(self):
        """/tools shows deprecation_note on a third line for deprecated tools."""
        from clive_telegram.bot import handle_tools

        rows = [
            _tool_row(
                tool_name="old_route",
                deprecated=True,
                deprecation_note="use navigation_v2 instead",
            )
        ]
        update = _make_update()
        context = _make_context()
        mock_pool = _make_pool(fetch_result=rows)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tools(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "[deprecated]" in text
        assert "Deprecated: use navigation_v2 instead" in text

    @pytest.mark.asyncio
    async def test_tools_registry_error_returns_unavailable_message(self):
        """/tools returns registry-unavailable message on DB exception (UX spec 4.2)."""
        from clive_telegram.bot import handle_tools

        update = _make_update()
        context = _make_context()
        mock_pool = _make_pool(raise_exc=Exception("connection refused"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tools(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Tool registry is unavailable" in text

    @pytest.mark.asyncio
    async def test_tools_unauthenticated_ignored(self):
        """/tools from non-owner is silently ignored (D-057)."""
        from clive_telegram.bot import handle_tools

        update = _make_update()
        context = _make_context()

        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await handle_tools(update, context)

        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /tool_disable — D-138 criterion 5, D-006
# ---------------------------------------------------------------------------

class TestHandleToolDisable:
    @pytest.mark.asyncio
    async def test_no_args_returns_usage_hint(self):
        """/tool_disable with no argument returns usage hint (UX spec 2.2)."""
        from clive_telegram.bot import handle_tool_disable

        update = _make_update()
        context = _make_context(args=[])

        with patch("clive_telegram.bot.is_authenticated", return_value=True):
            await handle_tool_disable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage:" in text
        assert "/tool_disable" in text
        assert "/tools" in text

    @pytest.mark.asyncio
    async def test_tool_not_found_returns_not_found_message(self):
        """/tool_disable with unknown name returns not-found message (UX spec 2.3)."""
        from clive_telegram.bot import handle_tool_disable

        update = _make_update()
        context = _make_context(args=["nonexistent_tool"])
        mock_pool = _make_pool(fetchrow_result=None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_disable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "No tool named nonexistent_tool is registered" in text
        assert "/tools" in text

    @pytest.mark.asyncio
    async def test_already_disabled_returns_already_disabled(self):
        """/tool_disable on a disabled tool returns already-disabled (UX spec 2.4)."""
        from clive_telegram.bot import handle_tool_disable

        row = _tool_row(tool_name="web_search", enabled=False)
        update = _make_update()
        context = _make_context(args=["web_search"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_disable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "web_search is already disabled" in text

    @pytest.mark.asyncio
    async def test_enabled_tool_sends_confirmation_prompt(self):
        """/tool_disable on enabled tool sends confirmation gate prompt (UX spec 2.5, D-006)."""
        import clive_telegram.bot as bot_module
        from clive_telegram.bot import handle_tool_disable

        row = _tool_row(
            tool_name="web_search",
            display_name="Web Search",
            version="1.0.0",
            description="Searches the web for current information",
            enabled=True,
        )
        update = _make_update()
        context = _make_context(args=["web_search"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_disable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Disable web_search?" in text
        assert "Web Search · v1.0.0" in text
        assert "Searches the web for current information" in text
        assert "When disabled, this tool will be unavailable until re-enabled." in text
        assert "/confirm_action" in text
        assert "/cancel_action" in text

        # Pending state stored
        assert CHAT_ID in bot_module._pending_tool_ops
        assert bot_module._pending_tool_ops[CHAT_ID]["op"] == "disable"
        assert bot_module._pending_tool_ops[CHAT_ID]["tool_name"] == "web_search"

    @pytest.mark.asyncio
    async def test_registry_error_returns_unavailable_message(self):
        """/tool_disable returns registry-unavailable on DB exception (UX spec 4.2)."""
        from clive_telegram.bot import handle_tool_disable

        update = _make_update()
        context = _make_context(args=["web_search"])
        mock_pool = _make_pool(raise_exc=Exception("DB down"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_disable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Tool registry is unavailable" in text

    @pytest.mark.asyncio
    async def test_unauthenticated_ignored(self):
        """/tool_disable from non-owner is silently ignored (D-057)."""
        from clive_telegram.bot import handle_tool_disable

        update = _make_update()
        context = _make_context(args=["web_search"])

        with patch("clive_telegram.bot.is_authenticated", return_value=False):
            await handle_tool_disable(update, context)

        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /tool_enable — D-138 criterion 5, D-006
# ---------------------------------------------------------------------------

class TestHandleToolEnable:
    @pytest.mark.asyncio
    async def test_no_args_returns_usage_hint(self):
        """/tool_enable with no argument returns usage hint (UX spec 3.2)."""
        from clive_telegram.bot import handle_tool_enable

        update = _make_update()
        context = _make_context(args=[])

        with patch("clive_telegram.bot.is_authenticated", return_value=True):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage:" in text
        assert "/tool_enable" in text
        assert "/tools" in text

    @pytest.mark.asyncio
    async def test_tool_not_found_returns_not_found_message(self):
        """/tool_enable with unknown name returns not-found message (UX spec 3.3)."""
        from clive_telegram.bot import handle_tool_enable

        update = _make_update()
        context = _make_context(args=["no_such_tool"])
        mock_pool = _make_pool(fetchrow_result=None)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "No tool named no_such_tool is registered" in text
        assert "/tools" in text

    @pytest.mark.asyncio
    async def test_already_enabled_returns_already_enabled(self):
        """/tool_enable on an enabled non-deprecated tool returns already-enabled (UX spec 3.4)."""
        from clive_telegram.bot import handle_tool_enable

        row = _tool_row(tool_name="web_search", enabled=True, deprecated=False)
        update = _make_update()
        context = _make_context(args=["web_search"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "web_search is already enabled" in text

    @pytest.mark.asyncio
    async def test_already_enabled_deprecated_includes_note(self):
        """/tool_enable on enabled+deprecated tool includes deprecation note (UX spec 3.4)."""
        from clive_telegram.bot import handle_tool_enable

        row = _tool_row(
            tool_name="old_tool",
            enabled=True,
            deprecated=True,
            deprecation_note="use new_tool instead",
        )
        update = _make_update()
        context = _make_context(args=["old_tool"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "old_tool is already enabled" in text
        assert "deprecated" in text
        assert "use new_tool instead" in text

    @pytest.mark.asyncio
    async def test_disabled_tool_sends_confirmation_prompt(self):
        """/tool_enable on disabled tool sends confirmation gate prompt (UX spec 3.5, D-006)."""
        import clive_telegram.bot as bot_module
        from clive_telegram.bot import handle_tool_enable

        row = _tool_row(
            tool_name="reminder",
            display_name="Reminder",
            version="1.0.0",
            description="Set timed reminders and notifications",
            enabled=False,
            deprecated=False,
        )
        update = _make_update()
        context = _make_context(args=["reminder"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Enable reminder?" in text
        assert "Reminder · v1.0.0" in text
        assert "Set timed reminders and notifications" in text
        assert "This tool will be available immediately." in text
        assert "/confirm_action — confirm enable" in text
        assert "/cancel_action" in text

        # Pending state stored
        assert CHAT_ID in bot_module._pending_tool_ops
        assert bot_module._pending_tool_ops[CHAT_ID]["op"] == "enable"
        assert bot_module._pending_tool_ops[CHAT_ID]["tool_name"] == "reminder"

    @pytest.mark.asyncio
    async def test_disabled_deprecated_tool_sends_deprecated_prompt(self):
        """/tool_enable on disabled+deprecated tool shows deprecated variant (UX spec 3.6)."""
        from clive_telegram.bot import handle_tool_enable

        row = _tool_row(
            tool_name="old_route",
            display_name="Calculate Route",
            version="0.3.0",
            description="Route planning between locations",
            enabled=False,
            deprecated=True,
            deprecation_note="use navigation_v2 instead",
        )
        update = _make_update()
        context = _make_context(args=["old_route"])
        mock_pool = _make_pool(fetchrow_result=row)

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Enable old_route?" in text
        assert "Calculate Route · v0.3.0 [deprecated]" in text
        assert "Deprecated: use navigation_v2 instead" in text
        assert "/confirm_action — enable anyway" in text  # "enable anyway" per UX spec 3.6
        assert "This tool will be available immediately." not in text  # absent in deprecated variant

    @pytest.mark.asyncio
    async def test_registry_error_returns_unavailable_message(self):
        """/tool_enable returns registry-unavailable on DB exception (UX spec 4.2)."""
        from clive_telegram.bot import handle_tool_enable

        update = _make_update()
        context = _make_context(args=["web_search"])
        mock_pool = _make_pool(raise_exc=Exception("DB timeout"))

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot.get_pool", return_value=mock_pool),
        ):
            await handle_tool_enable(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Tool registry is unavailable" in text


# ---------------------------------------------------------------------------
# Confirmation gate flow — /confirm_action and /cancel_action with tool ops
# ---------------------------------------------------------------------------

class TestToolConfirmationGate:
    @pytest.mark.asyncio
    async def test_confirm_action_with_tool_disable_emits_admin_tool_disable(self):
        """/confirm_action with pending tool disable emits admin.tool_disable (D-006)."""
        from clive_telegram.bot import handle_confirm_action

        op_data = {"op": "disable", "tool_name": "web_search", "deprecated": False}
        pending = {CHAT_ID: op_data}
        confirmed = {}

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", pending),
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_confirm_action(update, context)

        # Emits admin.tool_disable (not action.owner_response)
        mock_emit.assert_called_once()
        event_type = mock_emit.call_args.args[0]
        payload = mock_emit.call_args.args[1]["payload"]
        assert event_type == "admin.tool_disable"
        assert payload["tool_name"] == "web_search"
        assert payload["confirmed"] is True

        # State moved from pending to confirmed
        assert CHAT_ID not in pending
        assert CHAT_ID in confirmed

        # No immediate reply — success message comes via admin.tool_updated push
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_action_with_tool_enable_emits_admin_tool_enable(self):
        """/confirm_action with pending tool enable emits admin.tool_enable."""
        from clive_telegram.bot import handle_confirm_action

        op_data = {"op": "enable", "tool_name": "reminder", "deprecated": False}
        pending = {CHAT_ID: op_data}
        confirmed = {}

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", pending),
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_confirm_action(update, context)

        event_type = mock_emit.call_args.args[0]
        payload = mock_emit.call_args.args[1]["payload"]
        assert event_type == "admin.tool_enable"
        assert payload["tool_name"] == "reminder"
        assert payload["confirmed"] is True
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_action_no_tool_op_falls_through_to_generic(self):
        """/confirm_action with no tool op falls through to existing generic action handler."""
        from clive_telegram.bot import handle_confirm_action

        action_request_id = str(uuid.uuid4())

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", {}),
            patch("clive_telegram.bot._pending_action_generic", {CHAT_ID: action_request_id}),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_confirm_action(update, context)

        # Must emit action.owner_response (existing behaviour)
        mock_emit.assert_called_once()
        event_type = mock_emit.call_args.args[0]
        assert event_type == "action.owner_response"
        payload = mock_emit.call_args.args[1]["payload"]
        assert payload["confirmed"] is True

    @pytest.mark.asyncio
    async def test_cancel_action_with_tool_disable_returns_cancelled_message(self):
        """/cancel_action with pending disable returns 'remains enabled' message (UX spec 2.5)."""
        from clive_telegram.bot import handle_cancel_action

        op_data = {"op": "disable", "tool_name": "web_search", "deprecated": False}
        pending = {CHAT_ID: op_data}

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", pending),
        ):
            await handle_cancel_action(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Cancelled. web_search remains enabled." == text

        # Pending state cleared
        assert CHAT_ID not in pending

    @pytest.mark.asyncio
    async def test_cancel_action_with_tool_enable_returns_cancelled_message(self):
        """/cancel_action with pending enable returns 'remains disabled' message (UX spec 3.5)."""
        from clive_telegram.bot import handle_cancel_action

        op_data = {"op": "enable", "tool_name": "reminder", "deprecated": False}
        pending = {CHAT_ID: op_data}

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", pending),
        ):
            await handle_cancel_action(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Cancelled. reminder remains disabled." == text

    @pytest.mark.asyncio
    async def test_cancel_action_no_tool_op_falls_through_to_generic(self):
        """/cancel_action with no tool op falls through to existing generic action handler."""
        from clive_telegram.bot import handle_cancel_action

        action_request_id = str(uuid.uuid4())

        update = _make_update()
        context = _make_context()

        with (
            patch("clive_telegram.bot.is_authenticated", return_value=True),
            patch("clive_telegram.bot._pending_tool_ops", {}),
            patch("clive_telegram.bot._pending_action_generic", {CHAT_ID: action_request_id}),
            patch("clive_telegram.bot._emit_to_orchestrator", new_callable=AsyncMock) as mock_emit,
            patch("clive_telegram.bot.sessions") as mock_sessions,
        ):
            mock_sessions.get_or_create.return_value = uuid.uuid4()
            await handle_cancel_action(update, context)

        # Must emit action.owner_response with confirmed=False (existing behaviour)
        mock_emit.assert_called_once()
        payload = mock_emit.call_args.args[1]["payload"]
        assert payload["confirmed"] is False


# ---------------------------------------------------------------------------
# deliver_tool_updated — success message delivery (UX spec 2.6 / 3.7)
# ---------------------------------------------------------------------------

class TestDeliverToolUpdated:
    @pytest.mark.asyncio
    async def test_disable_success_sends_disabled_message(self):
        """admin.tool_updated after disable sends '{tool_name} disabled.' (UX spec 2.6)."""
        from clive_telegram.bot import deliver_tool_updated

        confirmed = {CHAT_ID: {"op": "disable", "tool_name": "web_search", "deprecated": False}}
        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        with (
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._app", mock_app),
        ):
            await deliver_tool_updated({}, CHAT_ID)

        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert text == "web_search disabled."
        assert CHAT_ID not in confirmed

    @pytest.mark.asyncio
    async def test_enable_success_sends_enabled_message(self):
        """admin.tool_updated after enable sends '{tool_name} enabled.' (UX spec 3.7)."""
        from clive_telegram.bot import deliver_tool_updated

        confirmed = {CHAT_ID: {"op": "enable", "tool_name": "reminder", "deprecated": False}}
        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        with (
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._app", mock_app),
        ):
            await deliver_tool_updated({}, CHAT_ID)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert text == "reminder enabled."

    @pytest.mark.asyncio
    async def test_enable_deprecated_success_includes_deprecated_note(self):
        """admin.tool_updated after enable of deprecated tool includes note (UX spec 3.7)."""
        from clive_telegram.bot import deliver_tool_updated

        confirmed = {CHAT_ID: {"op": "enable", "tool_name": "old_route", "deprecated": True}}
        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        with (
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._app", mock_app),
        ):
            await deliver_tool_updated({}, CHAT_ID)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert text == "old_route enabled. Note: this tool is deprecated."

    @pytest.mark.asyncio
    async def test_fallback_to_payload_when_no_confirmed_state(self):
        """deliver_tool_updated falls back to payload fields when _confirmed_tool_ops is empty."""
        from clive_telegram.bot import deliver_tool_updated

        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        payload = {"tool_name": "web_search", "operation": "disable", "deprecated": False}

        with (
            patch("clive_telegram.bot._confirmed_tool_ops", {}),
            patch("clive_telegram.bot._app", mock_app),
        ):
            await deliver_tool_updated(payload, CHAT_ID)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "web_search" in text


# ---------------------------------------------------------------------------
# deliver_tool_error — error delivery (UX spec 4.2)
# ---------------------------------------------------------------------------

class TestDeliverToolError:
    @pytest.mark.asyncio
    async def test_tool_error_sends_unavailable_message(self):
        """admin.tool_error sends registry-unavailable message (UX spec 4.2)."""
        from clive_telegram.bot import deliver_tool_error

        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        with patch("clive_telegram.bot._app", mock_app):
            await deliver_tool_error({}, CHAT_ID)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert text == "Tool registry is unavailable. Try again shortly."

    @pytest.mark.asyncio
    async def test_tool_error_clears_confirmed_state(self):
        """deliver_tool_error clears any _confirmed_tool_ops entry for the chat."""
        from clive_telegram.bot import deliver_tool_error

        confirmed = {CHAT_ID: {"op": "disable", "tool_name": "web_search"}}
        mock_bot = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot

        with (
            patch("clive_telegram.bot._confirmed_tool_ops", confirmed),
            patch("clive_telegram.bot._app", mock_app),
        ):
            await deliver_tool_error({}, CHAT_ID)

        assert CHAT_ID not in confirmed
