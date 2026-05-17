# Block 3 — UI/UX Design Document v0.11

**Status:** Accepted (v0.11 — D-147 AC-9)
**Date:** 2026-05-17
**Blocks:** 2, 3, 4, 5

---

## 1. Design Philosophy

CLIVE's UI is not a product UI. It is an owner interface — precise, low-noise,
and built for a single user who already knows what CLIVE is. The design
principles are:

- **No chrome for chrome's sake.** Every element earns its place by serving
  a functional need. Decorative UI is removed.
- **Response-first.** The query/response flow is always one click from any
  state. The owner does not navigate to ask a question.
- **Dark and calm.** Dark background, muted colour palette, readable
  monospace for CLIVE's responses. No bright call-to-action colours.
- **No page reloads.** All state transitions are in-page. The SPA model.
- **Fail visible.** Errors are shown inline, clearly, without modal dialogs.
  Pending states have explicit progress indicators.

---

## 2. Surface Inventory

| Surface | Medium | Auth | Live at |
|---|---|---|---|
| Telegram bot | Mobile/desktop app | Channel identity (D-057) | v0.1 |
| Web dashboard | Browser SPA | DASHBOARD_SECRET session cookie | v0.11 |

The web dashboard is the primary surface added in v0.11. It is served at
`clive.halmshaw.co.uk` via Caddy reverse proxy (HTTPS, Let's Encrypt).

---

## 3. Web Dashboard — Screen Inventory

### 3.1 Login Screen

**Trigger:** Any request without a valid session cookie redirects here.

**Elements:**
- CLIVE wordmark (text, not image — no external assets)
- Password input (type="password", autocomplete="current-password")
- Submit button ("Enter")
- Error message area (shown on 401; hidden otherwise)

**Behaviour:**
- POST to `/auth/login` with `{ "secret": "<value>" }`
- On 200: redirect to `/` (dashboard root)
- On 401: show "Access denied." inline (no redirect, no page reload)
- On 500: show "Authentication service unavailable." inline
- Session cookie is HTTP-only, SameSite=Lax, Secure in production
- No "remember me" toggle — 30-day session is the default and is not configurable from the UI

**Non-goals:** No username field. No registration. No password reset.
This is single-owner; the only credential is the shared secret.

---

### 3.2 Main Dashboard

**Layout:** Single-page application with three tabs:

```
┌─────────────────────────────────────────────────────┐
│  CLIVE                              [Logout]         │
├───────────────┬─────────────────────────────────────┤
│  Query  Pending  History                            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  (tab content)                                      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Global header:**
- "CLIVE" text mark (top-left)
- "Logout" link (top-right) — POST `/auth/logout`, redirect to login

---

### 3.3 Query Tab (default)

**Purpose:** Send a query to CLIVE and receive a response. Functionally
equivalent to the Telegram chat interface.

**Elements:**
- Conversation display area — scrollable, shows alternating user/CLIVE turns
- Query textarea — multi-line, placeholder "Ask CLIVE…"
- Send button — disabled while a response is pending
- Status indicator — "Waiting…" with 1s polling animation while pending

**Behaviour:**
1. Owner types query and presses Send (or Ctrl+Enter)
2. POST `/api/query` → returns `{ conversation_id, event_id }`
3. UI polls GET `/api/response?conversation_id=<id>` at 1s intervals
4. On 202 (pending): show "Waiting…" indicator, continue polling
5. On 200 (ready): display response in conversation area, stop polling
6. On error: show inline error, re-enable Send button

**Conversation display:**
- User turns: right-aligned, muted background
- CLIVE turns: left-aligned, slightly lighter background, monospace font
- Turns accumulate until page reload — no persistent client-side history (server-side is in `conversation_turns`)
- Max displayed turns: 50 (older turns scroll off the top)

**Constraints:**
- Max query length: 2000 characters (enforced client-side; server also validates)
- One in-flight query at a time — Send is disabled until response arrives
- New conversation_id per page session (no manual conversation switching in Query tab — use History tab)

---

### 3.4 Pending Tab

**Purpose:** Show Block 9 actions awaiting owner confirmation.
Equivalent to the Telegram confirm/cancel flow but accessible from browser.

**Elements:**
- List of pending actions — each row shows:
  - Action type badge (e.g. "web_search", "reminder", "delete_document")
  - Action description (human-readable intent)
  - Expires at (relative time, e.g. "expires in 4m")
  - Confirm button (green)
  - Cancel button (red)
- "No pending actions" empty state when list is empty
- Auto-refresh every 15 seconds

**Behaviour:**
- On load and every 15s: GET `/api/pending` → updates list in place
- Confirm: POST `/api/confirm` with `{ action_request_id }`
  - Emits `action.owner_response` with `decision="confirmed"` to Block 13
  - Row removed from list immediately (optimistic update)
- Cancel: POST `/api/cancel` with `{ action_request_id }`
  - Emits `action.owner_response` with `decision="rejected"` to Block 13
  - Row removed from list immediately

**D-006 compliance:** All confirm/cancel actions route through Block 13
via the event bus. The dashboard never directly modifies `pending_actions`.

---

### 3.5 History Tab

**Purpose:** Review past conversation turns by conversation UUID.

**Elements:**
- UUID input field with "Load" button
- Conversation display (same component as Query tab, read-only)
- "No conversation found" state on 404

**Behaviour:**
- Owner pastes a conversation_id UUID into the input field
- Clicks "Load"
- GET (proxied through `/api/history?conversation_id=<uuid>`) → Block 13 `/retrieve/conversation-history`
- Conversation turns displayed oldest-first
- Up to 50 turns shown

**Non-goals:** No search, no date-browsing, no list of all conversations.
Conversation IDs are obtained from Telegram (CLIVE includes them in structured
responses when asked, or from the `/status` command output).

---

## 4. Colour Palette

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#1a1a1a` | Page background |
| `--surface` | `#242424` | Card/panel background |
| `--surface-alt` | `#2c2c2c` | Alternate row, user turn |
| `--border` | `#333` | Borders, dividers |
| `--text` | `#e0e0e0` | Primary text |
| `--text-muted` | `#888` | Secondary text, timestamps |
| `--accent` | `#4a9eff` | Links, active tab indicator |
| `--confirm` | `#2d6a2d` | Confirm button background |
| `--cancel` | `#6a2d2d` | Cancel button background |
| `--error` | `#ff6b6b` | Error messages |

No external fonts. System font stack: `system-ui, -apple-system, sans-serif`.
Monospace stack for CLIVE responses: `'Courier New', Courier, monospace`.

---

## 5. Interaction States

| State | Visual |
|---|---|
| Idle | Normal — Send enabled, Pending auto-refreshes |
| Query pending | Send disabled, "Waiting…" text, 1s poll active |
| Confirm/cancel in-flight | Buttons disabled for that row, row fades |
| Session expired | 401 response → redirect to login |
| Network error | Inline red error text; retry button where appropriate |
| Empty state | Friendly text: "No pending actions." / "Ask CLIVE anything." |

---

## 6. Accessibility

- All interactive elements reachable via keyboard tab order
- Buttons have explicit `type` attributes
- Form submission via Enter key (query textarea: Ctrl+Enter to avoid accidental send)
- No colour-only state indicators — text labels accompany all status indicators
- Viewport meta: `width=device-width, initial-scale=1`

---

## 7. Security Constraints

- Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` (enforced by Caddy HTTPS)
- No secrets in JavaScript — login secret is sent via POST body, not URL parameter
- No local storage of sensitive data
- CSP header: `default-src 'self'` (no external CDN, no inline scripts from user content)
- Dashboard secret validation uses `secrets.compare_digest` (timing-safe)

---

## 8. Non-Goals for v0.11

The following are explicitly out of scope. They are not deferred — they
require a separate scope decision:

- Mobile-native dashboard (PWA, responsive breakpoints beyond minimal)
- WebSocket-based push (polling is sufficient for single-owner, low-frequency use)
- Multi-conversation management UI
- File upload via dashboard (Telegram /ingest is the ingest surface)
- Admin tools via dashboard (Block 19 is a separate surface decision)
- Notification system in dashboard (alerts arrive via Telegram; dashboard is pull-only for now)

---

## 9. Block Ownership Summary

| Concern | Owner block |
|---|---|
| Dashboard HTTP service, session auth | Block 2 |
| UX design principles, screen inventory | Block 3 (this document) |
| Egress routing (surface delivery) | Block 4 (egress.py in Block 13) |
| Session persistence, state sync | Block 5 (web_sessions table) |
| Event routing, retrieval endpoints | Block 13 |
| Action confirmation lifecycle | Block 9 |

---

*Block 3 UX Design — v0.11 — CLIVE*
