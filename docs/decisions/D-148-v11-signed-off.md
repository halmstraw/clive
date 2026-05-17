---
id: D-148
title: CLIVE v0.11 signed off — all ten criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 2, Block 3, Block 4, Block 5, Block 13, Block 23, Block 27, Block 28
agents: Architect
---

## Context

D-146 approved v0.11 scope (Multi-Surface + Sync/State). D-147 defined ten acceptance
criteria. The v0.11 implementation was committed in:

  6f28417 feat: v0.11 Block 2/3/4/5 — web dashboard + Block 4 egress + Block 5 sync/state (D-146/D-147)

D-148 was not recorded at that time; the gap was caught during v0.12 sign-off review.
This decision records sign-off retroactively against the D-147 criteria.

## Verification

All ten D-147 acceptance criteria verified present in the codebase:

**AC-1 — Dashboard service exists and is deployable**
`src/dashboard/` contains a FastAPI Python service with Dockerfile and `pyproject.toml`.
Dashboard service is in `docker-compose.yml` on port 8084 with healthcheck.

**AC-2 — Dashboard accessible at clive.halmshaw.co.uk**
`infrastructure/observability/caddy/Caddyfile` has a `clive.halmshaw.co.uk` block
reverse-proxying to `dashboard:8084`.

**AC-3 — Dashboard authentication via session token**
Session auth implemented in `src/dashboard/clive_dashboard/`. `clive_state.web_sessions`
table provisioned by `21_v11_web_sessions.sql`. `/api/*` endpoints require valid session.

**AC-4 — Owner can submit queries and receive responses via dashboard**
`POST /api/query` emits QUERY_RECEIVED with `source_surface: "dashboard"`. Block 4
egress routes QUERY_RESPONSE back. Frontend polls `/api/response?conversation_id=xxx`.

**AC-5 — Pending confirmations visible and actionable from dashboard**
`GET /api/pending`, `POST /api/confirm/<id>`, `POST /api/cancel/<id>` implemented.
Action lifecycle routes through Block 13 — D-006 preserved.

**AC-6 — Conversation history shared across surfaces**
Dashboard calls `/retrieve/conversation-history`. Queries from either surface share the
same `conversation_id` lookup from `clive_state.conversation_turns`.

**AC-7 — Block 4 is a real distinct egress component**
`src/orchestrator/orchestrator/egress.py` exists. `push.py` uses egress functions for
all surface delivery. Surface URLs come from `TELEGRAM_SERVICE_URL` and
`DASHBOARD_SERVICE_URL` environment variables.

**AC-8 — Block 5 closes: conversation state consistency model defined and implemented**
`21_v11_web_sessions.sql` exists (idempotent). Consistency model: last-write-wins on
conversation turns; strong consistency on confirmation gate decisions via pending_actions.
`source_surface` field in QUERY_RECEIVED payloads routes responses to originating surface.

**AC-9 — Block 3 closes: UX design document exists for both surfaces**
`docs/spec/Block 3 - UX Design v0.11.md` covers Telegram command reference, web
dashboard interface specification, consistency behaviour, and error states.

**AC-10 — CI passes**
`src/dashboard/tests/` contains `test_v11_dashboard_api.py` and
`test_v11_dashboard_auth.py`. `21_v11_web_sessions.sql` uses `CREATE TABLE IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`, GRANT patterns. Compose dry-run includes dashboard.

## Decision

v0.11 is signed off. All ten acceptance criteria met.

**Blocks formally closed by this version:**
- Block 2 (Multi-Surface) — web dashboard is the second surface
- Block 3 (UI/UX) — UX design document covers both surfaces and all commands
- Block 4 (Interface/Egress) — egress.py is a real distinct component
- Block 5 (Sync/State) — consistency model implemented and documented

## Related Decisions

- D-146 — v0.11 scope
- D-147 — v0.11 acceptance criteria
- D-135 — Block 26 gated (not required for v0.11)
- D-003 — Event bus principle (dashboard uses Block 13, not direct DB)
- D-006 — Confirmation gate (preserved in dashboard confirm/cancel flow)
