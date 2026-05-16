# CLIVE — v1 Roadmap

**Last updated:** 2026-05-16  
**Highest decision ID at time of writing:** D-136  
**Current version:** v0.7 signed off (D-133)

---

## Scope of v1

v1 is Blocks 1–29 of the CLIVE specification, minus two explicitly gated items:

- **Block 21 (Evolution Engine)** — paused per D-042. Requires Blocks 17, 10,
  6/7, and 24 to be solid. Activating it without that substrate would produce a
  system that evolves faster than alignment can be verified. Unblocked by
  explicit owner decision after v1.0 signs off.
- **Block 26 (Physical Device/Edge Node)** — gated per D-135. Depends on
  Blocks 2 and 5 which do not exist yet. Hardware is also qualitatively
  different work. Unblocked by explicit owner decision after Blocks 2 and 5
  are complete.
- **Blocks 30–38 (Business Layer)** — out of v1 scope per D-036.

---

## Where we are

### Implemented (signed off)

| Block | Name |
|---|---|
| 1 | Personality / Identity |
| 8 | Query / RAG |
| 9 | Action Layer (web search + reminders + deletion) |
| 11 | Memory Management (cross-session) |
| 13 | Central Orchestrator / Event Bus |
| 14 | Ingestion |
| 15 | Processing |
| 16 | Storage |
| 18 | Feedback / Correction |
| 20 | Cost / Rate Management |
| 22 | Alignment Layer |
| 23 | Telegram Surface |
| 25 | Observability |
| 27 | Infrastructure / IaC |
| 28 | CI/CD |

**15 of 29 in-scope blocks fully done.**

### Partial

| Block | Name | Status |
|---|---|---|
| 3 | UI/UX | Tool management commands (/tools, /tool_disable, /tool_enable) specified in Block 3 Tool Management UX Design v0.1 (v0.8). All other Telegram commands — query, ingest, delete, feedback, status — functional but not UX-specified. Single surface only. Full close at v0.11: second surface live, UX design covering both surfaces and all commands. |
| 4 | Interface/Egress | Collapsed into Block 23; not a distinct component (becomes real in v0.11) |
| 12 | Context Window | Dynamic allocation works inside Block 8; no standalone policy document |
| 19 | Config/Admin | Secrets + system doc activation only; no conversational control plane |
| 29 | Documentation | DECISIONS.md + specs + runbooks exist; CLIVE cannot query its own docs |

### Not started

| Block | Name | Planned version |
|---|---|---|
| 2 | Multi-Surface / Ambient Presence | v0.11 |
| 5 | Sync / State Layer | v0.11 |
| 6 | Users | v0.10 |
| 7 | Trust Zones / Tenancy | v0.10 |
| 10 | Workers / Background Agents | v0.9 |
| 17 | Tool / Plugin Registry | v0.8 |
| 21 | Evolution Engine | Gated (post-v1) |
| 24 | Sandboxing | Stub in v1.0; full implementation post-v1 |
| 26 | Physical Device / Edge Node | Gated (D-135) |

---

## Version Plan

### v0.8 — Tool Registry + Admin Stub

**Blocks:** 17 (primary), 19 (stub)  
**Theme:** Give Block 9 and Block 10 a registry to operate against before either
grows further.

**Why now:** Block 9 currently has three hardcoded action types. Every new
action added without a registry increases alignment surface area and audit
complexity. Block 10 (Workers) cannot be properly scoped until there is a
registry for workers to register in. This is a structural integrity item, not
a feature.

**Done when:**
- Registry table in PostgreSQL: tool name, version, description, permission
  scope, health status, enabled/disabled, deprecation record
- All current Block 9 actions (web search, reminder, delete) are registered
  entries
- Block 8 queries the registry at runtime to determine available actions —
  no hardcoded action list
- Block 13 rejects actions for unregistered tools before dispatch
- Telegram commands: `/tools` (list registered tools), `/tool_disable <name>`,
  `/tool_enable <name>`
- CI passes

**Partial block progress:** Block 19 gets its first real capability (tool
management via Telegram). Block 3 gets deliberate UX design for tool management
commands.

---

### v0.9 — Workers / Background Agents

**Blocks:** 10 (primary), 12 (closes partial)  
**Theme:** Proactive intelligence. CLIVE starts doing things without being asked.

**Why now:** Block 17 exists, so workers can register and be auditable. Workers
are the most visible gap between "well-engineered personal assistant" and
"ambient presence." The daily digest directly addresses the JARVIS ambition.

**Done when:**
- Worker framework: a worker is a registered Block 17 entry with a declared
  schedule, trigger type, and execution scope
- Block 13 can schedule and trigger workers on cron or event triggers
- Workers cannot exceed their declared scope — out-of-scope capability attempts
  are rejected by Block 13
- **Daily digest worker:** runs on schedule, delivers a summary of recent
  queries, actions taken, cost, feedback, and system health via Telegram
- **Knowledge maintenance worker:** runs weekly, identifies chunks with no
  retrieval hits above a configurable age threshold, flags them for owner
  review via Block 9 confirmation gate (no autonomous deletion — D-006)
- Worker outcomes logged to Block 16 and visible in Grafana
- Block 12 closes: a standalone context budget allocation policy document
  exists and is enforced by Block 8
- CI passes

---

### v0.10 — Users + Trust Zones

**Blocks:** 6, 7  
**Theme:** Formalise the single-owner model before any second surface touches it.

**Why now:** Blocks 6 and 7 must be real before Block 2/5 (Multi-Surface/Sync)
work begins. Every surface, worker, and tool query in v0.11 will need to be
zone-scoped. Channel-as-authentication (D-057) is appropriate for a
single-user system but the schema migration must happen while there is only
one user and one zone to migrate.

**Done when:**
- `users` table: owner record with Telegram ID bound, role = owner
- `zones` table: "personal" zone declared, all existing documents tagged to it
- Block 8 retrieval explicitly filters by zone on every query (enforced, not
  implicit)
- Block 9 actions zone-scoped at execution time
- Block 17 tool registrations include zone permissions field (populated for
  all existing tools)
- `/whoami` Telegram command returns user profile and zone access
- Adding a second user is possible in schema but not exposed via UI
- Zone boundaries are integration-tested in CI
- CI passes

---

### v0.11 — Multi-Surface + Sync/State

**Blocks:** 2, 5 (primary); 3, 4 (closes partials)  
**Theme:** CLIVE becomes an ambient presence, not just a Telegram bot.

**Second surface:** Lightweight web dashboard, hosted on the CLIVE VM behind
Caddy reverse proxy (consistent with Grafana at grafana.halmshaw.co.uk).
Decision: D-136.

**Why now:** Requires Blocks 6 and 7 to be solid. Block 4 (Interface/Egress)
becomes a real distinct component when two surfaces share an egress layer —
it cannot be built until there are two surfaces.

**Done when:**
- Web dashboard exists and is accessible at a subdomain behind Caddy
- Dashboard authenticates via the user record (Block 6)
- Owner can submit queries and receive responses from the dashboard
- Pending Block 9 confirmation requests are visible and actionable from
  the dashboard (not only via Telegram)
- Conversation history is shared: queries from either surface appear in the
  same history view
- Block 4 is a real distinct egress component used by both Block 23 and
  the web dashboard
- Block 3 closes: deliberate UX design documented for both surfaces and
  all commands
- Block 5 closes: conversation state sync is implemented with a defined
  consistency model (last-write-wins on conversation state; strong
  consistency on confirmation gate decisions)
- CI passes

---

### v0.12 — Config/Admin Complete + CLIVE Self-Knowledge

**Blocks:** 19 (completes partial), 29 (closes partial)  
**Theme:** Close all partial blocks. The owner can configure CLIVE
conversationally, and CLIVE can describe itself accurately.

**Why now:** By v0.12 there is a tool registry, workers running, two surfaces,
and users/zones. The control plane now has something worth controlling, and
Block 29 can close because Block 10 workers provide the operational state
CLIVE needs to answer questions about itself.

**Done when:**
- Owner can ask "what documents do you know about?", "what tools do you have?",
  "what actions did you take this week?" — answered from live Block 16 state
- Conversational configuration: add/remove ingestion sources, adjust worker
  schedules via natural language confirmed through Block 9 gate
- System health (cost, latency, error rate) queryable conversationally, not
  only via Grafana
- All configuration changes versioned and logged to audit trail in Block 16
- Block 19 formally closed
- Block 29 formally closed
- CI passes

---

### v1.0 — Hardening + Block 24 Stub

**Blocks:** 24 (stub)  
**Theme:** Production readiness. This is not a feature release.

**Why:** v1.0 is the sign-off gate for the full specification. It closes
Block 24 with a stub (sandboxing framework in the codebase, isolated,
IaC-ready, not yet active) so that Block 21 (Evolution Engine) can be
unblocked in v2 without an infrastructure sprint. All partial blocks are
formally confirmed closed. A full security review runs before sign-off.

**Done when:**
- Full security review complete: Block 23 authentication model reviewed
  across all surfaces, secrets management audit, DB role privileges audit,
  no outstanding P1/P2 findings
- Block 24 sandboxing stub: isolated framework in codebase, experimental
  environment IaC templates deployable on command, not yet active
- All 29 in-scope blocks are either Done or formally gated with a recorded
  decision (Blocks 21 and 26)
- v1.0 acceptance criteria defined as a formal decision before the version
  starts (per the established pattern)
- Owner signs off

---

## Summary

| Version | Blocks | Theme |
|---|---|---|
| **v0.8** | 17, 19 stub | Tool Registry |
| **v0.9** | 10, 12 close | Workers + Background Agents |
| **v0.10** | 6, 7 | Users + Trust Zones |
| **v0.11** | 2, 5, 3 close, 4 close | Multi-Surface + Sync/State (web dashboard) |
| **v0.12** | 19 complete, 29 close | Config/Admin + Self-Knowledge |
| **v1.0** | 24 stub, hardening | Security audit + production readiness |

**Gated (post-v1):**
- Block 21 (Evolution Engine) — activate after v1.0, requires Blocks 17, 10,
  6/7, 24 all solid
- Block 26 (Physical Device) — activate after Blocks 2/5 complete + hardware
  readiness decision (D-135)

---

*Maintained alongside the project. Update via recorded decision only.*
