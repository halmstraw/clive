---
id: D-139
title: CLIVE v0.8 signed off — all six criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 17, Block 8, Block 13, Block 23, Block 19, Block 3, Block 28
agents: Architect
---

## Context

v0.8 scope was approved in D-137. Six acceptance criteria were defined in
D-138. All implementation waves were completed and committed on 16–17 May 2026.

## Options Considered

Not applicable — sign-off decision records a verified outcome.

## Decision

CLIVE v0.8 is signed off. All six D-138 criteria were simultaneously true
at time of sign-off on 17 May 2026:

1. ✅ **AC-1 — Tool registry table in PostgreSQL**
   `clive_state.tool_registry` created by
   `infrastructure/sql/init/12_v08_tool_registry.sql`. Fields: tool_name
   (PK), display_name, version, description, permission_scope (TEXT[]),
   health_status (constrained), enabled, deprecated, deprecation_note,
   registered_at, updated_at. Auto-update trigger on updated_at. Index on
   (enabled, deprecated) for fast runtime lookups. Fully idempotent.

2. ✅ **AC-2 — All three Block 9 actions registered**
   `infrastructure/sql/init/13_v08_tool_registry_seed.sql` inserts
   `web_search`, `reminder`, and `delete_document` with ON CONFLICT DO NOTHING.
   All three rows present in the registry at runtime.

3. ✅ **AC-3 — Block 8 queries registry at runtime; no hardcoded action list**
   `src/query/query/registry.py` fetches all enabled, non-deprecated tools
   from `clive_state.tool_registry` with a 60-second TTL cache. The LLM
   system prompt is assembled with the live tool list (name + description only;
   permission_scope never exposed to LLM). Unrecognised or disabled tool intents
   return "That capability is not currently available." without emitting an event.

4. ✅ **AC-4 — Block 13 rejects action events for unregistered/disabled tools**
   `src/orchestrator/orchestrator/registry.py` wraps Block 9 action handlers
   via `make_gated_handler()`. Gate queries `clive_state.tool_registry` before
   every dispatch. Rejects with `action.rejected` event for:
   `tool_not_registered`, `tool_disabled`, `tool_deprecated`. All rejections
   logged at WARN with tool_name, reason, and original_event_id.
   `admin.tool_disable` and `admin.tool_enable` event handlers update the
   registry and emit `admin.tool_updated` / `admin.tool_error`.

5. ✅ **AC-5 — Telegram commands /tools, /tool_disable, /tool_enable live**
   All three commands implemented in `src/telegram/`. `/tools` lists all
   registered tools (name, status, version, description). `/tool_disable <name>`
   and `/tool_enable <name>` route through the Block 9 confirmation gate (D-006)
   before emitting `admin.tool_disable` / `admin.tool_enable` to Block 13.
   Both commands handle not-found, already-disabled/enabled states and show
   deprecation_note when enabling a deprecated tool. Owner-only access enforced.
   `/help` updated to include all three commands.

6. ✅ **AC-6 — CI passes**
   All test suites pass. Block 13 tests cover registry gate rejections (3
   reasons), admin enable/disable success, admin tool_not_found. Block 8 tests
   cover empty-registry and populated-registry prompt assembly. Block 23 tests
   cover /tools list, /tool_disable and /tool_enable confirmation flows, not-found
   cases. SQL init files are idempotent.

## Partial block progress delivered alongside v0.8

**Block 19 (Config/Admin):** First real conversational capability shipped —
tool enable/disable via Telegram. Status document produced at
`docs/spec/Block 19 - Config Admin Current State.md`. Full conversational
control plane deferred to v0.12 (requires Block 10 and Blocks 2/5 first).

**Block 3 (UI/UX):** UX design document produced for the three tool management
commands at `docs/spec/Block 3 - Tool Management UX Design.md`. Post-v0.8
consistency audit confirmed implementation matches the design document with
no discrepancies. Roadmap entry updated.

## Consequences

- Block 17 (Tool / Plugin Registry) is fully implemented.
- Block 9 (Action Layer) has no hardcoded action list — the registry is the
  single source of truth for available capabilities.
- Adding a new action in future requires only a tool_registry INSERT and a
  corresponding handler implementation. No Block 8 or Block 13 changes needed
  to recognise new tools.
- The alignment surface area for Block 9 is now bounded and auditable — every
  enabled capability is a visible row in the registry.
- Block 10 (Workers, v0.9) has a registry to register in before its scope grows.

## Related Decisions

- D-137 — v0.8 scope
- D-138 — v0.8 acceptance criteria
- D-133 — v0.7 Block 9 signed off
- D-006 — confirmation gate (D-006 compliance verified for /tool_disable and /tool_enable)
