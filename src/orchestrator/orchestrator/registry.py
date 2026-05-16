"""Block 13 — Tool registry gate (v0.8, Block 17 integration, D-137).

Before dispatching action.pending to Block 9, this gate verifies the
requested tool is registered, enabled, and not deprecated in
clive_state.tool_registry.

Registry rejections emit action.rejected (existing event type) with payload:
  { "tool_name": <name>, "reason": <reason>, "original_event_id": <id> }

Rejection reasons:
  - "tool_not_registered" — no row found in tool_registry
  - "tool_disabled"       — row found but enabled = FALSE
  - "tool_deprecated"     — row found but deprecated = TRUE

Admin event handlers:
  handle_tool_disable — handles admin.tool_disable from Block 23
  handle_tool_enable  — handles admin.tool_enable from Block 23

Both emit admin.tool_updated on success, admin.tool_error if tool not found.

D-003: registry check is a DB read within Block 13's own execution context.
       Not a cross-block call — D-003 compliant.
D-006: admin events must carry confirmed=True in payload. Block 13 trusts
       this flag. Block 23 owns the confirmation UX flow.
D-025: rejection emits a new event; it is not a retry of the original.
D-137: no new DB connection pool is created — reuses an existing pool
       via set_pool(). Called from main.py after pool initialisation.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import asyncpg
import structlog

from . import audit
from .events.schema import AlignmentResult, CLIVEEvent
from .events.taxonomy import ACTION_REJECTED, ADMIN_TOOL_ERROR, ADMIN_TOOL_UPDATED

log = structlog.get_logger()

# Shared pool — injected from main.py via set_pool(); no new pool created (D-137).
_pool: asyncpg.Pool | None = None

# Mapping from action_type field in action.pending payload to tool_name in registry.
# Extended as new tools are registered in Block 17. Keys are the action_type strings
# Block 23 sends; values are the tool_name primary keys in clive_state.tool_registry.
_ACTION_TYPE_TO_TOOL: dict[str, str] = {
    "document.delete": "delete_document",
    "web.search": "web_search",
    "reminder.schedule": "reminder",
}


def set_pool(pool: asyncpg.Pool) -> None:
    """Bind the shared DB pool. Called from main.py after pool initialisation.

    No new asyncpg connection pool is created — this reuses an existing
    pool already established during orchestrator startup (D-137).
    """
    global _pool
    _pool = pool


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Registry pool not set — call set_pool() first")
    return _pool


def _resolve_tool_name(event: CLIVEEvent) -> str | None:
    """Extract tool_name from action event payload.

    Checks payload['tool_name'] first (explicit field takes precedence).
    Falls back to mapping from payload['action_type'] via _ACTION_TYPE_TO_TOOL.
    Returns None if tool_name cannot be resolved — caller decides how to proceed.
    """
    payload = event.payload
    explicit = payload.get("tool_name")
    if explicit:
        return str(explicit)
    action_type = payload.get("action_type", "")
    return _ACTION_TYPE_TO_TOOL.get(action_type)


async def _lookup_tool(tool_name: str) -> dict[str, Any] | None:
    """Query clive_state.tool_registry for tool_name.

    Returns a dict with 'enabled' and 'deprecated' keys, or None if not found.
    """
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT enabled, deprecated FROM clive_state.tool_registry WHERE tool_name = $1",
            tool_name,
        )
    return dict(row) if row else None


async def _emit_action_rejected(
    event: CLIVEEvent,
    tool_name: str,
    reason: str,
) -> None:
    """Emit action.rejected for a registry gate rejection.

    Logs at WARN level with tool_name, reason, and original_event_id.
    Payload follows the registry rejection schema (not the Block 9 action schema).
    """
    from .bus import bus as _bus  # noqa: PLC0415

    log.warning(
        "registry_gate_rejected",
        tool_name=tool_name,
        reason=reason,
        original_event_id=str(event.event_id),
    )
    rejection = CLIVEEvent(
        event_type=ACTION_REJECTED,
        source_block=13,
        conversation_id=event.conversation_id,
        payload={
            "tool_name": tool_name,
            "reason": reason,
            "original_event_id": str(event.event_id),
        },
    )
    await audit.write(rejection, AlignmentResult.PASS, "emitted")
    await _bus.publish(rejection)


def make_gated_handler(
    original_handler: Callable[[CLIVEEvent], Awaitable[None]],
) -> Callable[[CLIVEEvent], Awaitable[None]]:
    """Wrap a Block 9 action event handler with the tool registry gate.

    For each incoming event:
    1. Resolve tool_name from payload (explicit field or action_type mapping).
    2. Query clive_state.tool_registry for that tool_name.
    3. Emit action.rejected and return if the tool is:
         - not registered (no row found)
         - disabled (enabled = FALSE)
         - deprecated (deprecated = TRUE)
    4. Call original_handler if all checks pass.

    If tool_name cannot be resolved (unknown action_type), passes through with
    a warning — Block 9 handles unknown action_types gracefully and the unknown
    type is not a registry concern.
    """

    async def gated(event: CLIVEEvent) -> None:
        tool_name = _resolve_tool_name(event)

        if tool_name is None:
            # Unresolvable tool — let Block 9 handle it (may be a future action_type
            # not yet in the mapping; Block 9 will warn on unknown action_type).
            log.warning(
                "registry_gate_unresolvable_tool",
                event_id=str(event.event_id),
                action_type=event.payload.get("action_type", ""),
            )
            await original_handler(event)
            return

        row = await _lookup_tool(tool_name)

        if row is None:
            await _emit_action_rejected(event, tool_name, "tool_not_registered")
            return

        if not row["enabled"]:
            await _emit_action_rejected(event, tool_name, "tool_disabled")
            return

        if row["deprecated"]:
            await _emit_action_rejected(event, tool_name, "tool_deprecated")
            return

        # All checks passed — dispatch to Block 9.
        await original_handler(event)

    return gated


async def _do_tool_update(
    tool_name: str,
    enabled: bool,
    action_label: str,
    event: CLIVEEvent,
) -> None:
    """Shared logic: UPDATE tool_registry and emit result event.

    asyncpg returns a command tag string ("UPDATE N") from execute().
    N=0 means no row matched — tool_name not found.
    """
    from .bus import bus as _bus  # noqa: PLC0415

    pool = _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE clive_state.tool_registry
            SET enabled = $1, updated_at = NOW()
            WHERE tool_name = $2
            """,
            enabled,
            tool_name,
        )

    # Parse "UPDATE N" command tag; default to 0 on any unexpected format.
    try:
        updated_count = int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        updated_count = 0

    if updated_count > 0:
        log.info("admin_tool_updated", tool_name=tool_name, action=action_label)
        result_event = CLIVEEvent(
            event_type=ADMIN_TOOL_UPDATED,
            source_block=13,
            conversation_id=event.conversation_id,
            payload={"tool_name": tool_name, "action": action_label},
        )
        await audit.write(result_event, AlignmentResult.PASS, "emitted")
        await _bus.publish(result_event)
    else:
        log.warning("admin_tool_not_found", tool_name=tool_name, action=action_label)
        error_event = CLIVEEvent(
            event_type=ADMIN_TOOL_ERROR,
            source_block=13,
            conversation_id=event.conversation_id,
            payload={"tool_name": tool_name, "reason": "tool_not_found"},
        )
        await audit.write(error_event, AlignmentResult.PASS, "emitted")
        await _bus.publish(error_event)


async def handle_tool_disable(event: CLIVEEvent) -> None:
    """Handle admin.tool_disable emitted by Block 23.

    D-006: confirmed=True is required in payload. Block 13 trusts this flag;
           Block 23 owns the confirmation UX and will not emit this event
           without explicit owner approval.

    Updates tool_registry: enabled = FALSE, updated_at = NOW().
    Emits admin.tool_updated { tool_name, action: "disabled" } on success.
    Emits admin.tool_error { tool_name, reason: "tool_not_found" } if not found.
    """
    payload = event.payload
    tool_name = payload.get("tool_name", "")
    confirmed = payload.get("confirmed", False)

    if not confirmed:
        log.warning(
            "admin_tool_disable_not_confirmed",
            tool_name=tool_name,
            event_id=str(event.event_id),
        )
        return

    if not tool_name:
        log.warning("admin_tool_disable_missing_tool_name", event_id=str(event.event_id))
        return

    await _do_tool_update(tool_name, enabled=False, action_label="disabled", event=event)


async def handle_tool_enable(event: CLIVEEvent) -> None:
    """Handle admin.tool_enable emitted by Block 23.

    D-006: confirmed=True is required in payload. Block 13 trusts this flag;
           Block 23 owns the confirmation UX and will not emit this event
           without explicit owner approval.

    Updates tool_registry: enabled = TRUE, updated_at = NOW().
    Emits admin.tool_updated { tool_name, action: "enabled" } on success.
    Emits admin.tool_error { tool_name, reason: "tool_not_found" } if not found.
    """
    payload = event.payload
    tool_name = payload.get("tool_name", "")
    confirmed = payload.get("confirmed", False)

    if not confirmed:
        log.warning(
            "admin_tool_enable_not_confirmed",
            tool_name=tool_name,
            event_id=str(event.event_id),
        )
        return

    if not tool_name:
        log.warning("admin_tool_enable_missing_tool_name", event_id=str(event.event_id))
        return

    await _do_tool_update(tool_name, enabled=True, action_label="enabled", event=event)
