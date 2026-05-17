---
id: D-143
title: CLIVE v0.10 scope — Blocks 6 (Users) and 7 (Trust Zones)
status: Accepted
date: 2026-05-17
blocks: Block 6 (Users), Block 7 (Trust Zones), Block 8 (Query/RAG), Block 9 (Action Layer), Block 16 (Storage), Block 17 (Tool Registry), Block 23 (Telegram Surface), Block 28 (CI/CD)
agents: Access & Security Agent, Intelligence Agent, Knowledge Agent, Infrastructure Agent
---

## Context

v0.9 delivers Block 10 (Workers) and closes Block 12 (Context Window). The v1
roadmap (v1-roadmap.md) defines v0.10 as Users + Trust Zones, with the rationale
that Blocks 6 and 7 must exist before any second surface (v0.11) touches the
identity model. The channel-as-authentication model (D-057) is appropriate for a
single-owner system, but the schema migration from implicit hardcoded zones and
env-var auth to a proper user/zone model must happen while there is only one user
and one zone to migrate.

## Options Considered

A. v0.10 = Blocks 6 + 7 as scoped in v1-roadmap.md — accepted.
B. v0.10 = Block 24 (Sandboxing stub) first — rejected. Block 24 serves Block 21
   (Evolution Engine, paused). No users/zones means v0.11 Multi-Surface work has
   no identity substrate. Sequencing Block 24 before Block 6/7 would create a
   worse dependency chain.
C. v0.10 = Block 2 (Multi-Surface) first — rejected. Block 2 requires Blocks 6/7
   per roadmap dependency. Cannot build two-surface auth without a user model.

## Decision

v0.10 scope is Blocks 6 (Users) and 7 (Trust Zones), implemented as:

- clive_state.users table: owner and future viewer records, Telegram chat ID binding
- clive_state.zones table: named zone records ('personal' seeded)
- clive_state.tool_registry: zone_permissions TEXT[] column added
- clive_state.pending_actions: zone_scope TEXT column added
- Block 8: zone_scope validated against zones table before retrieval; invalid zones
  rejected before any DB query runs
- Block 9: zone_scope propagated from requesting event into pending_actions rows
- Block 23: /whoami command; is_authenticated() backed by users table with env var
  bootstrap fallback
- Second-user capability in schema (role TEXT CHECK includes 'viewer') but not
  exposed via any Telegram command
- CI zone boundary integration tests

## Rationale

The identity model is the foundation every surface and worker query stands on.
Completing it before adding a second surface (v0.11) avoids a retrofitting sprint
that would touch every authenticated path in the codebase. The migration is small
now (one user, one zone) and grows in complexity with each new surface added.

## Consequences

- v0.11 (Multi-Surface) can assume a proper users table exists and extend it
  without schema migration.
- Block 23 auth becomes DB-backed rather than env-var-only; env var becomes a
  bootstrap/fallback mechanism only.
- Block 8 retrieval gains zone existence validation (previously any string was
  accepted as zone_scope with no validation against known zones).
- All tool registry entries will carry zone_permissions; Block 8 can enforce
  tool availability by zone in a future sprint.
- Block 21 (Evolution Engine, gated) will find a users/zones model ready when
  activated.

## Related Decisions

D-001 — Single-owner system
D-050 — Block 16 single zone at v0.1; zone enforcement active from day one
D-057 — Channel-as-authentication; env var owner check
D-135 — Block 26 gated
D-136 — v0.11 second surface is web dashboard
