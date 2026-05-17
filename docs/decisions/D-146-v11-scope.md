---
id: D-146
title: CLIVE v0.11 scope — Multi-Surface + Sync/State (web dashboard)
status: Accepted
date: 2026-05-17
blocks: Block 2, Block 3, Block 4, Block 5, Block 13, Block 23, Block 27, Block 28
agents: Architect, Experience Agent, Systems Agent, Access & Security Agent, Infrastructure Agent
---

## Context

v0.10 is signed off (D-145). Blocks 6 and 7 are in production. The `clive_state.users`
and `clive_state.zones` tables exist. Block 23 authentication is DB-backed.

v0.11 is next per the roadmap. It requires Blocks 6 and 7 to be solid (now done).
Block 4 (Interface/Egress) cannot be a real distinct component until there are two
surfaces to route between. Block 5 (Sync/State) cannot be scoped until there is
shared state to synchronise. Block 2 (Multi-Surface) is the second surface itself.
Block 3 (UI/UX) closes its partial with a UX design that covers both surfaces.

## Decision

v0.11 scope is approved. Theme: CLIVE becomes an ambient presence, not just a
Telegram bot.

**Primary blocks:** 2 (Multi-Surface), 5 (Sync/State)
**Closes partials:** 3 (UI/UX), 4 (Interface/Egress)

**Second surface:** Lightweight web dashboard hosted on the CLIVE VM behind Caddy,
consistent with Grafana at grafana.halmshaw.co.uk. Subdomain: clive.halmshaw.co.uk.
This was pre-decided in D-136.

**Block 4 — Interface/Egress:** A new `egress.py` module in Block 13's orchestrator
package becomes Block 4. It maintains a surface registry (Telegram → port 8082,
Dashboard → port 8084) and provides `push_to_surface()` and `push_to_all_surfaces()`
functions. push.py is refactored to use egress.py for all surface delivery.
Both Block 23 and the dashboard receive pushes via the egress layer.

**Block 5 — Sync/State:** Conversation state consistency model is defined and
implemented. Last-write-wins on conversation turns (both surfaces write to
`clive_state.conversation_turns`; the query.received event carries `source_surface`
to route the response to the originating surface). Strong consistency on
confirmation gate decisions (pending_actions is the single source of truth;
both surfaces read and write through Block 13 — D-006 is preserved). A
`web_sessions` table stores dashboard session tokens. All Block 5 state
lives in PostgreSQL — no separate sync service.

**Block 2 — Multi-Surface:** New Python service `src/dashboard/` running FastAPI
on port 8084. Served at `clive.halmshaw.co.uk` via Caddy. Authentication via
session token derived from `DASHBOARD_SECRET` (set in secrets.env). Owner can
submit queries, view conversation history, and action pending confirmations.

**Block 3 — UI/UX design document:** Covers both surfaces (Telegram + web
dashboard) and all commands. Closes the Block 3 partial.

**Source surface routing:** QUERY_RECEIVED events carry `source_surface` in
payload ("telegram" or "dashboard"). Block 13 egress layer uses this to route
QUERY_RESPONSE to the originating surface only. Alert and confirmation events
are broadcast to all surfaces.

## Consequences

- A new `dashboard` container is added to docker-compose.yml.
- Caddyfile gains a `clive.halmshaw.co.uk` entry.
- deploy.yml builds and deploys the dashboard image.
- Block 13 push.py is refactored; no behaviour change for Telegram surface.
- A new SQL init file (21_v11_web_sessions.sql) adds the web_sessions table.
- Block 4 is no longer "collapsed into Block 23" — it is a named module in Block 13.
- Block 3 formally closes with a UX design document.
- Block 5 formally closes with a defined consistency model and web_sessions table.

## Related Decisions

- D-136 — v0.11 second surface is a lightweight web dashboard
- D-145 — v0.10 signed off (prerequisite)
- D-003 — Event bus principle (all inter-block communication via Block 13)
- D-006 — Confirmation gate (dashboard confirm/cancel must go through Block 13)
- D-050 — Single zone 'personal' (web sessions scoped to personal zone)
- D-057 — Channel-as-authentication (extended: dashboard uses DASHBOARD_SECRET)
