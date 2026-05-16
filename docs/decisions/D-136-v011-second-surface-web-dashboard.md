# D-136 — v0.11 second surface is a lightweight web dashboard

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks affected:** Block 2 (Multi-Surface/Ambient Presence), Block 5 (Sync/State Layer), Block 4 (Interface/Egress), Block 3 (UI/UX)  
**Recorded by:** Architect

---

## Context

The v1 roadmap (docs/v1-roadmap.md) includes v0.11 as the Multi-Surface +
Sync/State version. That version requires a second surface to be defined before
the Experience Agent can be briefed and implementation can begin.

The Architect identified two candidate surfaces for v0.11: a Mac menu bar app
or a lightweight web dashboard. The owner selected the web dashboard.

---

## Decision

The second surface for v0.11 is a lightweight web dashboard.

The dashboard is the second entry point into CLIVE alongside the Telegram bot.
It must:
- Authenticate via the user record established in Block 6 (v0.10)
- Allow the owner to submit queries and receive responses
- Display pending Block 9 confirmation requests so they can be approved or
  cancelled from the dashboard (not only from Telegram)
- Show conversation history shared with the Telegram surface (read-only view
  of prior turns)
- Be hosted on the CLIVE VM and accessible via the Caddy reverse proxy
  (consistent with how Grafana is exposed at grafana.halmshaw.co.uk)

Scope boundaries for v0.11:
- The dashboard is a query-and-confirm surface; it is not a full admin
  interface (that is Block 19, completed in v0.12)
- Mobile-responsive is desired but not a v0.11 acceptance criterion
- No native app is built; browser-based only

The specific technology choice (framework, rendering approach) is delegated
to the Experience Agent during v0.11 planning, consistent with D-002
(no technology choices at specification stage).

---

## Alternatives considered

**Mac menu bar app** — considered but rejected at owner direction. A web
dashboard is cross-platform, does not require native distribution, and is
simpler to deploy alongside existing Caddy infrastructure.

**Voice interface** — not considered for v0.11. Too large a scope jump; no
speech-to-text infrastructure exists.

---

## Impact

- Experience Agent is briefed for v0.11 using a web dashboard as the
  second surface
- Block 4 (Interface/Egress) becomes a real distinct component in v0.11
  because two surfaces now share an egress layer
- Caddy reverse proxy configuration (established in D-121) will be extended
  to serve the dashboard at a subdomain
- Block 23 (Telegram) remains the primary surface; the dashboard is additive
