---
id: D-153
title: CLIVE v1.0 acceptance criteria — eight criteria for sandboxing stub and security review
status: Accepted
date: 2026-05-17
blocks: Block 24, Block 23, Block 6, Block 7, Block 27, Block 28
agents: Architect
---

## Context

D-152 defines v1.0 scope. Acceptance criteria must be recorded before implementation
begins (D-008).

## Decision

v1.0 is done when ALL of the following are simultaneously true:

**AC-1 — Block 24 framework stub exists and is importable**
`src/sandboxing/` Python package exists with `__init__.py` and at minimum:
- `SandboxType` enum (e.g. PROCESS, CONTAINER) with docstring explaining each
- `SandboxSpec` dataclass: sandbox_type, capability_declarations (list[str]),
  execution_scope (zone name), max_duration_seconds (int)
- `SandboxRunner` abstract base class with `execute(spec: SandboxSpec) -> dict` method
- Module-level `SANDBOXING_ACTIVE: bool = False` — production paths must check this
  before attempting to use the sandbox runner

The package is importable in a clean Python environment (`import sandboxing` succeeds).
No production service imports it. No CI step activates it.

**AC-2 — Block 24 experimental IaC templates exist and are valid Terraform**
`infrastructure/terraform/experimental/` directory exists containing:
- `main.tf` — parameterised Hetzner VM provisioning for an experimental environment
  (server type, location, SSH key, labels as variables)
- `variables.tf` — input variables with descriptions and defaults
- `outputs.tf` — outputs: server IP, server ID
- `README.md` — instructions for deploying an experimental environment on command

`terraform validate` passes in the experimental directory (CI or manual verification).
The templates are NOT applied by default — they require explicit `terraform apply`.

**AC-3 — Block 24 Compose service defined but inactive by default**
`docker-compose.yml` includes a `sandbox` service definition gated behind the
`experimental` Compose profile. The service is not started by `docker compose up`
(no profile specified) or `docker compose --profile default up`. It is only
started by `docker compose --profile experimental up sandbox`. The service definition
includes a placeholder image reference and a clear comment explaining it is inactive
until Block 21 is activated.

**AC-4 — Security review: surface auth — no P1/P2 findings**
Telegram channel-as-auth (D-057) reviewed in the context of the two-surface model.
Finding documented: Telegram auth is appropriate for the single-owner model; the
owner chat ID check is enforced at the bot handler level on every message. Dashboard
session token reviewed: DASHBOARD_SECRET is injected from secrets.env (not hardcoded),
session cookie is HTTP-only with 30-day expiry, session lookup queries
`clive_state.web_sessions` (not in-memory). No P1 or P2 findings.

**AC-5 — Security review: secrets management — no P1/P2 findings**
All secrets come from `/etc/clive/secrets.env` (Ansible-injected). No secrets in
committed files. `.env.example` is current (all required keys documented, no actual
values). CI stub secrets pattern (D-084) reviewed and correct. No P1 or P2 findings.

**AC-6 — Security review: DB role privileges — no P1/P2 findings**
`clive_app` role: SELECT, INSERT, UPDATE on all application tables. No DELETE
(where not explicitly required). No CREATE/DROP. `clive_audit_writer` role: INSERT-only
on `clive_state.audit_log` (D-067). `postgres` superuser not used at runtime.
All role privilege grants reviewed against SQL init scripts. No P1 or P2 findings.

**AC-7 — Security review: network exposure — no P1/P2 findings**
Only Caddy (ports 80/443) and the GitHub Actions self-hosted runner agent are
internet-facing (D-090). Orchestrator (:8080), query (:8081), telegram (:8082),
dashboard (:8084), PostgreSQL (:5432), MinIO (:9000/:9001), and observability stack
ports are internal Docker network only. Firewall rules reviewed in Terraform/Ansible
config. No P1 or P2 findings.

**AC-8 — All 29 in-scope blocks confirmed Done or formally gated; CI passes**
The v1.0 sign-off decision (D-154) includes an explicit block-by-block status table
confirming all 29 blocks are either Done or gated with a recorded decision. No block
is left in an ambiguous "partial" state. CI passes with all existing tests plus any
new tests added for the Block 24 stub.

## Consequences

Sign-off decision (D-154) records when all eight criteria are verified. After D-154,
CLIVE v1 is complete. Block 21 (Evolution Engine) is formally unblocked for v2 (D-042).

## Related Decisions

- D-152 — v1.0 scope
- D-022 — Experimental zone on separate infrastructure
- D-029 — Parameterised IaC templates for experimental environments
- D-030 — Experimental events are a distinct trust class
- D-042 — Block 21 paused (unblocked by v1.0 sign-off)
- D-057 — Channel-as-authentication
- D-067 — Append-only audit log (INSERT-only role)
- D-084 — CI stub secrets pattern
- D-090 — Self-hosted runner (no inbound SSH)
