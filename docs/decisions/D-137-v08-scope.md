# D-137 — CLIVE v0.8 scope — Tool Registry + Admin Stub

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks affected:** 17 (primary), 19 (stub), 3 (partial), 8, 13, 23, 28

---

## Decision

v0.8 scope is:

- **Block 17 (Tool/Plugin Registry)** — primary delivery. A persistent
  registry of all tools available to Block 9, stored in PostgreSQL.
- **Block 19 (Config/Admin)** — first real capability. Tool enable/disable
  via Telegram commands constitutes the first conversational control plane
  action.
- **Block 3 (UI/UX)** — partial progress. Deliberate UX design for the
  three new tool management commands before implementation.
- **Blocks 8, 13, 23** — coordinated changes to support the registry:
  Block 8 queries the registry at runtime, Block 13 gates action dispatch
  against the registry, Block 23 surfaces the three new commands.

## Context

Block 9 currently has three hardcoded action types (web_search, reminder,
delete_document). Every new action added without a registry increases
alignment surface area and audit complexity. Block 10 (Workers, v0.9)
cannot be properly scoped until there is a registry for workers to register
in. This is a structural integrity item, not a feature.

## Consequences

- The tool_registry table becomes the single source of truth for what
  Block 9 (and later Block 10) may do.
- Block 8 loses its hardcoded action list.
- Block 13 gains a validation gate that rejects action events for
  unregistered or disabled tools.
- Block 19 is no longer purely infrastructure-managed; the owner gains
  runtime control of tool availability via Telegram.
- v0.9 (Workers) can proceed cleanly — worker registrations will use
  the same registry infrastructure.
