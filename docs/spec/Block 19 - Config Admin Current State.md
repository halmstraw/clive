*Systems Agent artefact — produced May 2026.*

---

# Block 19 — Config/Admin Current State

**Version:** v0.8 (current)
**Status:** Partial — first real capabilities delivered; conversational control plane not yet built
**Produced by:** Systems Agent
**Date:** May 2026
**Governing decisions:** D-006, D-049, D-079, D-137
**Closes:** v0.12 (see Section 3)

---

## Purpose of This Document

Block 19 (Config/Admin) is currently partial. This document records what it
provides as of v0.8, what it does not yet provide, the prerequisites that must
be in place before the remaining work is worth building, and the specific
capabilities v0.12 must deliver to formally close it.

This is a living status document. It is not a requirements document. The canonical
requirements work for Block 19 has not yet been completed; that will happen before
v0.12 begins.

---

## 1 — What Block 19 Currently Provides (v0.8)

### 1.1 Secrets Management

Secrets are Ansible-injected at deploy time via `/etc/clive/secrets.env` on the
production VM. All application containers receive secrets through Docker Compose
`env_file`. No secret is stored in code or committed to the repository.

**Scope:** This is infrastructure-layer configuration, not conversational
administration. The owner cannot change secrets via Telegram. Changing a secret
requires an Ansible re-deploy.

**Decisions:** The constraint that secrets come from `/etc/clive/secrets.env` is
enforced across the entire codebase as a non-negotiable implementation constraint.

**What this provides to the owner:** Reproducible, auditable secret management
at deploy time. Secrets do not drift between environments.

**What this does not provide:** Any runtime ability to update, rotate, or inspect
which secrets are currently in use. Rotation requires a deploy.

---

### 1.2 System Document Activation

The owner can activate a new version of a system document (personality, Block 1;
alignment rules, Block 22) via a two-step Telegram confirmation flow. This was
the first intentional Block 19 capability, introduced to support the core
requirement that system documents must never self-activate (D-049).

**Commands:**
- `/activate <document_type>` — Step 1. Looks up the pending inactive document
  for the given type, shows the owner the version ID and a content preview, then
  prompts for `/confirm_activate <version_id>`.
- `/confirm_activate <version_id>` — Step 2. Atomically deactivates the
  previously active version and activates the confirmed version in a single
  transaction. Emits a `config.changed` event to Block 13.

**Valid document types:** `personality`, `alignment_rules`

**Decisions:** D-049 (system document activation requires explicit two-step
owner confirmation), D-079 (same — two-step activation pattern formalised),
D-006 (no irreversible action without explicit human confirmation).

**What this provides to the owner:** The ability to safely swap in a new
personality or alignment rules document, with a preview before commitment and
an event trail after.

**What this does not provide:** Any ability to see the currently active document
content, view the activation history, or manage document types beyond personality
and alignment rules.

---

### 1.3 Tool Inspection — /tools

The owner can inspect the full state of the Block 17 (Tool Registry) via the
`/tools` command, introduced in v0.8.

**Command:** `/tools`

**What it returns:** A formatted list of all registered tools, ordered
alphabetically. Each entry shows: tool_name (as identifier), version, enabled
or disabled status, display name, one-line description. Deprecated tools carry
a third line with the deprecation note. Unhealthy tools (health_status not
nominal) surface the health state inline.

**Pagination:** If the full list exceeds 3,800 characters, sequential messages
are sent automatically. No user-driven pagination.

**Format:** Per Block 3 UX Design document (v0.1).

**Decisions:** D-137 (v0.8 scope includes Block 17 tool registry and these
three Telegram commands).

---

### 1.4 Tool Enable and Disable — /tool_disable and /tool_enable

The owner can disable or re-enable any registered tool via explicit two-step
confirmation, introduced in v0.8.

**Commands:**
- `/tool_disable <tool_name>` — Confirms the tool is currently enabled, then
  prompts for confirmation before any state change.
- `/tool_enable <tool_name>` — Confirms the tool is currently disabled, then
  prompts for confirmation. Deprecated tools receive an augmented prompt that
  surfaces the deprecation note.

**Confirmation gate:** Both commands require the owner to send `/confirm_action`
before the state change is executed. `/cancel_action` aborts. Timeout (Block 9
default) is treated as cancellation. This is a D-006 requirement — tool
enable/disable affects Block 9 action dispatch and is treated as a consequential
state change.

**Event path:** On confirmation, `admin.tool_disable` or `admin.tool_enable` is
emitted to Block 13, which routes to Block 17 for the registry update. Block 13
pushes `admin.tool_updated` (or `admin.tool_error`) back to Block 23 for delivery
to the owner. D-003 compliant throughout.

**State enforcement:** Block 13 rejects action events for disabled tools before
dispatch. Disabling a tool has immediate effect on Block 9 action routing.

**Error handling:** Tool not found, tool already in the requested state, and
registry unavailable are each handled with specific, named responses (per Block 3
UX design principles).

**Decisions:** D-137 (commands specified), D-006 (confirmation gate), D-003
(event bus — no direct block-to-block calls).

---

## 2 — What Block 19 Does Not Yet Provide

### 2.1 Conversational Configuration

The owner cannot configure CLIVE through natural language. There is no control
plane that accepts instructions like "add this RSS feed as an ingestion source"
or "run the daily digest at 8am instead of 7am" and translates them into
confirmed configuration changes.

All current Block 19 capabilities are explicit Telegram commands. The command
set is the control plane.

### 2.2 Ingestion Source Management

There is no way to add, remove, or list ingestion sources conversationally.
Documents are ingested via `/ingest` (one file at a time). There is no concept
of a persistent source — a URL, feed, or folder — that CLIVE monitors and
ingests from automatically.

This requires Block 10 (Workers) before it is meaningful: workers are the
execution substrate for scheduled ingestion jobs.

### 2.3 Worker Schedule Adjustment

Block 10 (Workers / Background Agents) does not exist yet (planned v0.9). There
are no worker schedules to adjust. When Block 10 ships, workers will have declared
schedules registered in Block 17. Block 19's conversational control plane will
need to be able to modify those schedules via confirmed actions. That capability
cannot be designed or built until the workers themselves exist.

### 2.4 System Health Queryable Conversationally

The `/status` command reports document count, last ingest, last query, and LLM
spend. Deeper system health — latency, error rates, block-level health signals
— is visible only via Grafana (Block 25, D-117). The owner cannot ask "what's
CLIVE's error rate this week?" and receive an answer from Block 16 state.

### 2.5 Configuration History

Configuration changes emit `config.changed` events to Block 13, which are logged
(D-134). However, the owner cannot query configuration history conversationally.
There is no "what did I change last week?" capability.

### 2.6 CLIVE Self-Knowledge

CLIVE cannot describe itself accurately from live state. The owner cannot ask
"what documents do you know about?" and get a complete answer from Block 16 — or
ask "what tools do you have?" and get a live registry response — or ask "what
actions did you take this week?" and get an account from operational logs. These
are Block 29 capabilities as much as Block 19, and both blocks close together
at v0.12.

---

## 3 — What v0.12 Must Add to Close Block 19

The v0.12 scope in `docs/v1-roadmap.md` defines the following done-when criteria
for Block 19:

1. **Conversational self-knowledge queries.** Owner can ask "what documents do
   you know about?", "what tools do you have?", "what actions did you take this
   week?" — answered from live Block 16 state, not from hard-coded responses.

2. **Conversational configuration.** Owner can add and remove ingestion sources,
   and adjust worker schedules, via natural language. All such changes are
   confirmed through the Block 9 gate before execution (D-006).

3. **Conversational health queries.** System health — cost, latency, error rate
   — is queryable via Telegram (and, in v0.12, via the web dashboard), not only
   via Grafana.

4. **Configuration change audit.** All configuration changes are versioned and
   logged to the audit trail in Block 16 (consistent with D-067 append-only
   audit pattern).

5. **Block 19 formally closed.** A sign-off decision is recorded. The partial
   entry is removed from the roadmap.

Note: v0.12 also closes Block 29 (Documentation). Both blocks require the same
substrate — live Block 16 state accessible to Block 8 — and they are designed
and delivered together.

---

## 4 — Interface Note: Why the Remaining Work Is Not Being Built Now

Every current Block 19 capability is a Telegram command. The owner types a
command; CLIVE responds. This is a simple, reliable pattern and it is the right
pattern for the capabilities that exist today.

The conversational control plane — the core of what Block 19 is meant to be —
requires a different substrate. It needs:

- **Block 10 (Workers, v0.9):** Worker schedules must exist before they can be
  adjusted. The conversational config interface would have nothing to configure
  without workers.

- **Block 17 (Tool Registry, v0.8 — now complete):** Tools must be registered
  before they can be managed. This prerequisite is now met.

- **Blocks 6 and 7 (Users/Trust Zones, v0.10):** Any multi-surface access to
  configuration must be zone-scoped and user-authenticated. The access model
  must be solid before configuration commands are exposed across more than one
  surface.

- **Blocks 2 and 5 (Multi-Surface/Sync, v0.11):** The web dashboard is the
  second surface on which conversational configuration will be available. It
  is not worth designing multi-surface config UX until the second surface exists.

v0.12 arrives after all four prerequisites are in place. The control plane then
has something worth controlling, the surfaces it needs to operate on, and the
access model it needs to enforce.

Building the conversational control plane before v0.12 would mean designing
against a substrate that does not yet exist. v0.12 is the right time.

---

## 5 — Decisions Relevant to Block 19

| Decision | Summary | Relevance |
|---|---|---|
| D-006 | Every irreversible action requires explicit owner confirmation | All Block 19 state-change commands gate through Block 9 |
| D-049 | System document activation requires two-step confirmation | Governs /activate and /confirm_activate |
| D-079 | Two-step activation pattern formalised | Same as D-049 — confirms the pattern |
| D-137 | v0.8 scope includes tool registry and Telegram tool management commands | Delivered Block 19's first real conversational capabilities |
| D-003 | All inter-block communication via Block 13 event bus | Tool enable/disable event path |
| D-134 | Event bus JSON logging per event | config.changed and admin.tool_* events are logged |
| D-117 | Block 25 observability stack | System health currently Grafana-only; closed by Block 19 v0.12 work |

---

*Block 19 — Config/Admin Current State*
*Systems Agent artefact. Update when Block 19 capabilities change or when v0.12 requirements work begins.*
