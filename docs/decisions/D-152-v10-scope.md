---
id: D-152
title: CLIVE v1.0 scope — Block 24 sandboxing stub + security review
status: Accepted
date: 2026-05-17
blocks: Block 24, Block 23, Block 6, Block 7, Block 27, Block 28, Block 29
agents: Architect
---

## Context

v0.12 signed off (D-151). All 29 in-scope blocks are either Done (26 blocks) or
formally gated with a recorded decision (Block 21 per D-042, Block 26 per D-135).

v1.0 is the production-readiness gate. This is not a feature release. The sole
remaining implementation item is Block 24 (Sandboxing), which requires a stub so
that the Evolution Engine (Block 21) can be unblocked in v2 without an infrastructure
sprint. The security review is mandatory before the specification can be declared
complete — two surfaces and a proper user model now exist, and neither has had a
formal auth review.

Owner approved v1.0 scope as option A.

## Decision

v1.0 scope is approved. Theme: production readiness. No new features.

**Block 24 — Sandboxing Stub:**

Block 24 must exist in the codebase as an isolated, inactive framework so that:
- Block 21 (Evolution Engine) can be unblocked post-v1 without an infrastructure sprint
- The sandboxing architecture is defined and reviewable before activation
- IaC templates for experimental environments are deployable on command if needed

v1.0 Block 24 deliverables:
1. `src/sandboxing/` Python package: framework interface defining sandbox types,
   capability declarations, and execution scope constraints. Not imported by any
   production path. No active container or process isolation in production.
2. `infrastructure/terraform/experimental/` directory: parameterised Terraform
   templates for experimental environment provisioning (per D-029). Deployable on
   command by the owner; not deployed by default.
3. Block 24 in docker-compose.yml: sandbox service defined but gated behind a
   Compose profile (`experimental`). Not started with the default `docker compose up`.

**Security Review:**

Scope is a structured audit of the security posture across all live surfaces and
infrastructure. The output is a findings record in the v1.0 sign-off decision (D-154).
v1.0 does not ship with any outstanding P1 (critical) or P2 (high) findings.

Review areas:
- **Surface auth:** Telegram channel-as-auth (D-057) reviewed against the current
  two-surface model. Dashboard session token: DASHBOARD_SECRET handling, HTTP-only
  cookie, 30-day expiry, session table cleanup.
- **Secrets management:** All secrets from `/etc/clive/secrets.env`. No secrets in
  code or committed files. CI stub secrets pattern (D-084) reviewed. `.env.example`
  current and accurate.
- **DB role privileges:** `clive_app` has SELECT/INSERT/UPDATE only (no DELETE except
  where explicit). `clive_audit_writer` has INSERT-only on `clive_state.audit_log`
  (D-067). No role has CREATE/DROP privileges outside init scripts.
- **Network exposure:** Only Caddy (ports 80/443) and the self-hosted runner are
  internet-facing. Orchestrator, query, telegram, dashboard, and DB ports are
  internal only.

**Block closure confirmation:**

All 29 in-scope blocks are formally confirmed Done or gated in D-154 (v1.0 sign-off).

## Delegation

- **Access & Security Agent** (Blocks 6, 7, 23, 24): Block 24 framework stub
  (`src/sandboxing/`) + security review across all four areas.
- **Infrastructure Agent** (Blocks 27, 28): Block 24 IaC templates
  (`infrastructure/terraform/experimental/`) + Compose experimental profile.

Both agents work in parallel. Cross-agent interface: the Compose experimental profile
definition. Access & Security Agent declares what the sandbox service needs (env vars,
network, volumes). Infrastructure Agent implements it in docker-compose.yml.

## Consequences

- Block 24 stub is in the codebase but not active — no production behaviour changes.
- Security review findings are recorded in D-154 before sign-off.
- After v1.0 sign-off, Block 21 (Evolution Engine) is formally unblocked for v2.

## Related Decisions

- D-042 — Block 21 paused (Evolution Engine — unblocked after v1.0)
- D-135 — Block 26 gated (Physical Device — unblocked after Blocks 2/5 + hardware)
- D-022 — Experimental zone on separate infrastructure
- D-029 — Block 21 uses parameterised IaC templates (Block 24 stub provides these)
- D-030 — Experimental events are a distinct trust class
- D-006 — Confirmation gate (Block 24 does not bypass this)
- D-151 — v0.12 signed off (prerequisite)
