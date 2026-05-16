# D-138 — CLIVE v0.8 acceptance criteria

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks affected:** 17, 8, 13, 23, 28

---

## Decision

v0.8 is done when all six criteria below are met:

1. **Registry table exists in PostgreSQL** with schema: tool_name (PK),
   display_name, version, description, permission_scope (array), health_status,
   enabled, deprecated, deprecation_note, registered_at, updated_at.
   SQL init file is idempotent.

2. **All three current Block 9 actions are registered entries** in the
   tool_registry table: web_search, reminder, delete_document. Seed data
   is in an idempotent SQL init file.

3. **Block 8 queries the registry at runtime** to determine available
   actions. No hardcoded action list remains in Block 8. The LLM prompt
   reflects the live registry. Unrecognised or disabled tool intents
   return "That capability is not currently available."

4. **Block 13 rejects action events for unregistered or disabled tools**
   before dispatch. Rejection emits an action.rejected event with reason
   field (tool_not_registered | tool_disabled | tool_deprecated).
   No silent drops.

5. **Three Telegram commands are live:**
   - /tools — lists all registered tools with enabled/disabled status
   - /tool_disable \<name\> — disables a tool; routes through Block 9
     confirmation gate (D-006)
   - /tool_enable \<name\> — enables a tool; routes through Block 9
     confirmation gate (D-006)

6. **CI passes** — SQL idempotency tests pass, unit tests for Block 8
   registry query, Block 13 rejection gate, and Block 23 new commands
   all pass.

## Context

Follows the established acceptance criteria pattern: D-103 (v0.2),
D-106 (v0.3), D-113 (v0.4), D-116 (v0.4 extended), D-123 (v0.5),
D-126 (v0.6), D-129 (v0.7), D-132 (v0.7 Block 9).

## Sign-off

v0.8 is signed off by a separate decision (D-139, to be recorded) once
all six criteria are confirmed met.
