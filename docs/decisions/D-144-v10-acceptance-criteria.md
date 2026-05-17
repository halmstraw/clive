---
id: D-144
title: CLIVE v0.10 acceptance criteria — ten criteria for Blocks 6 and 7 delivery
status: Accepted
date: 2026-05-17
blocks: Block 6 (Users), Block 7 (Trust Zones), Block 8 (Query/RAG), Block 9 (Action Layer), Block 16 (Storage), Block 17 (Tool Registry), Block 23 (Telegram Surface), Block 28 (CI/CD)
agents: Access & Security Agent, Intelligence Agent, Knowledge Agent, Infrastructure Agent
---

## Context

v0.10 scope accepted (D-143). Acceptance criteria record what "done" means for
this version, following the established pattern (D-106, D-113, D-116, D-123,
D-126, D-129, D-132, D-138, D-141).

## Options Considered

Single option: define a concrete, verifiable criterion set covering each
deliverable in D-143 scope.

## Decision

v0.10 is done when all ten of the following criteria are met:

1. **clive_state.users table exists** with: user_id UUID PRIMARY KEY, telegram_chat_id
   BIGINT UNIQUE NOT NULL, role TEXT NOT NULL CHECK (role IN ('owner', 'viewer')),
   zone_access TEXT[] NOT NULL DEFAULT ARRAY['personal'], created_at TIMESTAMPTZ NOT
   NULL DEFAULT NOW(). Schema is idempotent (CREATE TABLE IF NOT EXISTS). No owner
   row seeded in SQL — owner is registered by Block 23 at startup.

2. **clive_state.zones table exists** with: zone_name TEXT PRIMARY KEY, description
   TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(). 'personal' zone
   seeded in SQL init with ON CONFLICT DO NOTHING.

3. **tool_registry zone_permissions column**: clive_state.tool_registry has
   zone_permissions TEXT[] NOT NULL DEFAULT ARRAY['personal'] added via ALTER TABLE
   ADD COLUMN IF NOT EXISTS. All existing tool registry rows have zone_permissions =
   ARRAY['personal'] (UPDATE on seed re-run via ON CONFLICT DO UPDATE).

4. **pending_actions zone_scope column**: clive_state.pending_actions has zone_scope
   TEXT NOT NULL DEFAULT 'personal' added via ALTER TABLE ADD COLUMN IF NOT EXISTS.
   action.py propagates zone_scope from requesting event into the pending_actions row
   on insert.

5. **Block 8 zone validation**: before any retrieval SQL executes, zone_scope is
   validated against clive_state.zones; if the requested zone does not exist,
   retrieval returns empty results and emits a structured rejection log entry. No
   retrieval SQL runs against an unknown zone.

6. **Block 23 /whoami command**: returns the caller's telegram_chat_id, role, and
   zone_access as read from clive_state.users. If the user record does not exist
   (before first startup registration), returns a clear "not yet registered" message.

7. **Block 23 DB-backed authentication**: is_authenticated() checks an in-memory
   cache of allowed telegram_chat_ids, populated from clive_state.users on startup
   and refreshed every 60 seconds. TELEGRAM_OWNER_CHAT_ID env var is the bootstrap
   fallback only when the users table is empty or unreachable. First-run startup
   upserts the owner record from env var if not present.

8. **Second-user schema capability**: clive_state.users supports multiple rows
   (role = 'viewer' permitted by CHECK constraint); no Telegram command exposes
   viewer creation. Schema-only capability — verified by a DB-level assertion in CI.

9. **CI zone boundary integration test**: a query with zone_scope='nonexistent_zone'
   is rejected before retrieval (validated against zones table, returns empty result
   and logs rejection); asserted in the orchestrator integration test suite.

10. **CI passes**: all existing tests continue to pass; new tests cover /whoami
    command, owner startup registration, zone validation rejection, zone_scope
    propagation into pending_actions, and zone_permissions column presence on
    tool_registry rows.

## Rationale

Ten criteria map directly to the eight deliverables in D-143 scope plus CI
verification. Each criterion is independently verifiable — no criterion
requires subjective assessment.

## Consequences

When all ten criteria are met, the owner records D-145 (v0.10 signed off).
v0.11 (Multi-Surface, D-136) is then unblocked.

## Related Decisions

D-143 — v0.10 scope
D-050 — Zone enforcement active from day one
D-057 — Channel-as-authentication
D-006 — Confirmation gate (zone_scope propagation to pending_actions)
