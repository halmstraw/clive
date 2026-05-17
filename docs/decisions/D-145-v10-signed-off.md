---
id: D-145
title: CLIVE v0.10 signed off — all ten criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 6, Block 7, Block 8, Block 9, Block 16, Block 17, Block 23, Block 28
agents: Infrastructure Agent, Access & Security Agent, Intelligence Agent, Knowledge Agent, Architect
---

## Context

D-144 defined ten acceptance criteria for v0.10 (Blocks 6 and 7 — Users and
Trust Zones). All ten were verified by the Infrastructure Agent on 17 May 2026
before owner sign-off.

## Decision

CLIVE v0.10 is signed off. All ten D-144 acceptance criteria are simultaneously
true as of 17 May 2026.

AC-1 — `clive_state.users` table: created with `user_id` UUID PRIMARY KEY,
`telegram_chat_id` BIGINT UNIQUE NOT NULL, `role` TEXT NOT NULL CHECK
(role IN ('owner', 'viewer')), `zone_access` TEXT[] NOT NULL DEFAULT
ARRAY['personal'], `created_at` TIMESTAMPTZ NOT NULL DEFAULT NOW().
Schema is idempotent (`CREATE TABLE IF NOT EXISTS`). No owner row seeded
in SQL — owner registered by Block 23 at startup. SQL init file
`17_v10_users_zones.sql`.

AC-2 — `clive_state.zones` table: created with `zone_name` TEXT PRIMARY KEY.
'personal' zone seeded in `18_v10_zones_seed.sql` with `ON CONFLICT DO NOTHING`.

AC-3 — `tool_registry.zone_permissions` column: `TEXT[] NOT NULL DEFAULT
ARRAY['personal']` added via `ALTER TABLE ADD COLUMN IF NOT EXISTS` in
`19_v10_tool_registry_zone_permissions.sql`. All existing tool registry rows
backfilled to ARRAY['personal']. Column confirmed via CI test-db assertion.

AC-4 — `pending_actions.zone_scope` column: `TEXT NOT NULL DEFAULT 'personal'`
added via `ALTER TABLE ADD COLUMN IF NOT EXISTS` in
`20_v10_pending_actions_zone_scope.sql`. `action.py` extracts `zone_scope`
from requesting event payload (default 'personal') and writes it into the
`pending_actions` INSERT at line 133. Asserted by
`test_action_pending_insert_includes_zone_scope` and
`test_action_pending_defaults_zone_scope_to_personal`.

AC-5 — Block 8 zone validation: `retrieval.py` `_is_valid_zone()` queries
`clive_state.zones` before any retrieval SQL runs. Unknown zone returns
`{"ranked_chunks": [], "result_count": 0}` and emits `retrieval_unknown_zone`
warning log. No retrieval SQL runs against an invalid zone. Zone validation
applied to `retrieve()`, `retrieve_document_by_filename()`, and
`retrieve_document_list()`. Fail-open on DB error (pool None or exception).
Four test assertions in `test_v10_zone_validation.py`.

AC-6 — Block 23 `/whoami` command: `whoami_command` in `bot.py` returns the
caller's `telegram_chat_id`, `role`, `zone_access`, and `created_at` (Member
since) from `clive_state.users`. Returns "not yet registered" message when
`get_user_profile` returns None. Auth-gated by `is_authenticated()` — silent
ignore for unauthenticated callers. Two assertions in `test_v10_whoami.py`.

AC-7 — Block 23 DB-backed authentication: `auth.py` `is_authenticated()` checks
`_allowed_chat_ids` in-memory cache populated from `clive_state.users` at
startup via `refresh_auth_cache()`. Background loop `auth_cache_refresh_loop()`
refreshes every 60 seconds. `TELEGRAM_OWNER_CHAT_ID` env var is the fallback
when cache is empty or DB unreachable. `register_owner_if_absent()` upserts the
owner record from env var at startup using `ON CONFLICT DO NOTHING`. Four
assertions in `test_v10_auth.py`.

AC-8 — Second-user schema capability: `clive_state.users` `role` column CHECK
constraint includes `'viewer'`. No Telegram command exposes viewer creation.
Schema-only capability confirmed by `clive_state.users` table definition in
`17_v10_users_zones.sql` and the CI test-db "Assert owner user row exists"
step (confirms column types).

AC-9 — CI zone boundary integration test: `test_v10_zone_validation.py`
`test_retrieve_returns_empty_for_unknown_zone` asserts zone rejection before
retrieval. Five new assertions in the `test-db` CI job confirm: 'personal' zone
seeded, `clive_state.users` table and columns present, zero `tool_registry` rows
with NULL/empty `zone_permissions`, `pending_actions.zone_scope` column present,
and `clive_app` cannot CREATE tables (least-privilege check).

AC-10 — CI passes: All four new SQL init files idempotent (CREATE IF NOT EXISTS,
ADD COLUMN IF NOT EXISTS, ON CONFLICT DO NOTHING throughout; UPDATE backfill is
safe on re-run). CI glob `infrastructure/sql/init/*.sql | sort` picks up files
17–20 automatically. All required test assertions present across
`test_v10_zone_validation.py`, `test_v10_auth.py`, and `test_v10_whoami.py`.

## Consequences

- v0.10 is in production. CLIVE now has a proper user and zone identity model.
- Block 23 authentication is DB-backed; env var is a bootstrap fallback only.
- Block 8 retrieval enforces zone existence at query time — no retrieval runs
  against a zone that does not exist in `clive_state.zones`.
- Block 9 preserves zone context through the full action confirmation lifecycle.
- All tool registry entries carry `zone_permissions`; zone-aware tool enforcement
  is ready for a future sprint without further schema migration.
- Second-user capability exists in the schema. Adding a viewer requires only an
  INSERT into `clive_state.users` — no schema migration needed.
- v0.11 (Multi-Surface web dashboard, D-136) is unblocked. It can assume a
  proper `clive_state.users` table exists and extend it without schema migration.

## Related Decisions

- D-143 — v0.10 scope
- D-144 — v0.10 acceptance criteria
- D-050 — Zone enforcement active from day one
- D-057 — Channel-as-authentication
- D-006 — Confirmation gate (zone_scope propagation)
- D-136 — v0.11 second surface is web dashboard (now unblocked)
