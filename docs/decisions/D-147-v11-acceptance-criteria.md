---
id: D-147
title: CLIVE v0.11 acceptance criteria — ten criteria for Multi-Surface delivery
status: Accepted
date: 2026-05-17
blocks: Block 2, Block 3, Block 4, Block 5, Block 13, Block 23, Block 27, Block 28
agents: Architect
---

## Context

D-146 defines v0.11 scope. Acceptance criteria must be recorded before
implementation begins (D-008).

## Decision

v0.11 is done when ALL of the following are simultaneously true:

**AC-1 — Dashboard service exists and is deployable**
`src/dashboard/` contains a FastAPI Python service. `src/dashboard/Dockerfile`
builds successfully. `docker compose config` includes the dashboard service
on port 8084 with correct healthcheck.

**AC-2 — Dashboard accessible at clive.halmshaw.co.uk**
`infrastructure/observability/caddy/Caddyfile` has a `clive.halmshaw.co.uk`
block reverse-proxying to `dashboard:8084`. Caddy TLS is handled automatically.

**AC-3 — Dashboard authentication via session token**
Owner logs in at `/auth/login` with `DASHBOARD_SECRET` from secrets.env.
On correct secret, a session token is issued (32-byte hex, stored in
`clive_state.web_sessions`), set as an HTTP-only cookie with 30-day expiry.
All `/api/*` endpoints require a valid, non-expired session. Invalid or missing
session returns HTTP 401. Session token lookup queries `clive_state.web_sessions`.

**AC-4 — Owner can submit queries and receive responses via dashboard**
`POST /api/query` with authenticated session emits QUERY_RECEIVED to Block 13
with `source_surface: "dashboard"`. Block 13 routes QUERY_RESPONSE back to
the dashboard's push endpoint via Block 4 egress. Dashboard stores the response
in memory keyed by conversation_id. Frontend polls `/api/response?conversation_id=xxx`
until the assistant response is available.

**AC-5 — Pending confirmations visible and actionable from dashboard**
`GET /api/pending` (authenticated) returns pending Block 9 actions for the
owner's zone. `POST /api/confirm/<action_request_id>` and
`POST /api/cancel/<action_request_id>` emit action.owner_response to Block 13
via HTTP POST to `/events`. D-006 is preserved — Block 13 processes the
confirmation through the same action lifecycle as Telegram confirmations.

**AC-6 — Conversation history shared across surfaces**
Dashboard `GET /api/history?conversation_id=xxx` calls Block 13's
`/retrieve/conversation-history` endpoint which reads from
`clive_state.conversation_turns`. Queries submitted from Telegram appear
in the dashboard history and vice versa (same conversation_id lookup).

**AC-7 — Block 4 is a real distinct egress component**
`src/orchestrator/orchestrator/egress.py` exists. push.py uses egress functions
for all surface delivery (push_to_surface, push_to_all_surfaces). Neither
Block 13's push.py nor any other file hardcodes the Telegram or dashboard URL
outside egress.py. Surface URLs come from environment variables:
`TELEGRAM_SERVICE_URL` and `DASHBOARD_SERVICE_URL`.

**AC-8 — Block 5 closes: conversation state consistency model defined and implemented**
`clive_state.web_sessions` table exists (idempotent SQL in
`21_v11_web_sessions.sql`). Consistency model documented: last-write-wins on
conversation turns (both surfaces write via Block 13's push_response_to_surface
→ store_conversation_turn); strong consistency on confirmation gate decisions
(pending_actions is the single source of truth via Block 13). The `source_surface`
field in QUERY_RECEIVED payloads ensures responses return to the originating surface.

**AC-9 — Block 3 closes: UX design document exists for both surfaces**
`docs/spec/Block 3 - UX Design v0.11.md` covers: Telegram command reference
(all commands), web dashboard interface specification (all pages and interactions),
consistency behaviour between surfaces, and error states for both surfaces.

**AC-10 — CI passes**
- `src/dashboard/tests/` has unit tests covering session auth, query submission,
  and pending action listing; all pass.
- SQL idempotency: `21_v11_web_sessions.sql` uses CREATE TABLE IF NOT EXISTS,
  CREATE INDEX IF NOT EXISTS, GRANT patterns.
- `test-db` CI job: new step asserts `clive_state.web_sessions` table and
  columns exist.
- Compose dry-run includes dashboard service without error.
- deploy.yml builds and deploys dashboard image.

## Consequences

Sign-off decision (D-148) records when all ten criteria are verified.

## Related Decisions

- D-146 — v0.11 scope
- D-003 — Event bus principle
- D-006 — Confirmation gate
- D-025 — At-least-once delivery (dashboard push endpoint must be idempotent)
