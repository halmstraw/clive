---
id: D-154
title: CLIVE v1.0 signed off — all eight criteria met 17 May 2026
status: Accepted
date: 2026-05-17
blocks: Block 24, all blocks
agents: Architect, Access & Security Agent, Infrastructure Agent
---

## Context

D-152 approved v1.0 scope. D-153 defined eight acceptance criteria.
This decision records sign-off and the formal security review findings.

## Verification

**AC-1 — Block 24 framework stub exists and is importable**
`src/sandboxing/` Python package exists with:
- `__init__.py` — exports SANDBOXING_ACTIVE, SandboxType, SandboxSpec, SandboxRunner
- `types.py` — SandboxType enum (PROCESS, CONTAINER), SandboxSpec dataclass with
  validation, SandboxRunner abstract base class
- `pyproject.toml` — installable package with no production dependencies
- `tests/test_sandboxing_stub.py` — 10 tests covering production guard, type values,
  spec validation, and abstract enforcement
- `SANDBOXING_ACTIVE = False` — production paths cannot activate sandboxing without
  a recorded decision (D-042 gate)
- No production service imports the sandboxing package.

**AC-2 — Block 24 experimental IaC templates exist**
`infrastructure/terraform/experimental/` contains:
- `main.tf` — parameterised Hetzner VM provisioning (server_type, location,
  experiment_name, owner_ip variables). Separate S3 state key per experiment.
  State never touches the production state file (D-022).
- `variables.tf` — all inputs with descriptions, defaults, and validation rules
- `outputs.tf` — server_id, server_ip, experiment_name, firewall_id
- `README.md` — full init/plan/apply/destroy instructions with decision references
Not applied by default. Requires explicit `terraform init` + `terraform apply`
with per-experiment credentials.

**AC-3 — Block 24 Compose service defined but inactive by default**
`sandbox` service added to `docker-compose.yml` with `profiles: [experimental]`.
Not started by `docker compose up` or any current CI job. Only started by
`docker compose --profile experimental up sandbox`. SANDBOXING_ACTIVE=false
in service environment — aligns with AC-1 production guard.

**AC-4 — Security review: surface auth — no P1/P2 findings**
_Telegram (Block 23):_ `clive_telegram/auth.py` — owner chat ID check is DB-backed
(loaded from `clive_state.users` at startup, enforced per message). Single-owner
model is appropriate (D-057). Auth guard raises `RuntimeError` if
`TELEGRAM_OWNER_CHAT_ID` is not set — service does not start without it.
_Dashboard (Block 2):_ `DASHBOARD_SECRET` loaded from `secrets.env` with
`RuntimeError` if unset. Session cookie is `httponly=True`, 30-day expiry,
DB-backed (`clive_state.web_sessions`). Session token verified on every `/api/*`
request with DB lookup (not in-memory). No P1/P2 findings.

**AC-5 — Security review: secrets management — no P1/P2 findings**
All application code reads secrets via `os.environ.get()`. No hardcoded secret
values in any CLIVE source file (hits in `src/*/` grep are exclusively in
`.venv/` third-party library code). SQL init passwords use
`'PLACEHOLDER_REPLACED_BY_ANSIBLE'` pattern (D-093). `.env.example` is current
— lists all required secrets with no real values, clearly marked "never commit
real values." `DASHBOARD_SECRET` and `SEARCH_API_KEY` explicitly noted as
secrets.env-only values. No P1/P2 findings.

**AC-6 — Security review: DB role privileges — no P1/P2 findings**
`clive_app`: `GRANT ALL` on application tables in `clive_search` and `clive_state`.
This is intentional — Block 9 requires DELETE on chunks/documents for the deletion
workflow (D-006). The `clive_state.config` table is the exception: `GRANT SELECT,
INSERT, UPDATE` only (no DELETE — consistent with append-only audit principle).
`clive_audit_writer`: `GRANT INSERT, SELECT` on `clive_audit.event_log` only.
`REVOKE UPDATE, DELETE` explicitly called in `04_audit_table.sql` (D-067).
The `clive_audit.event_log` table is physically append-only at the DB layer.
`postgres` superuser: used only at DB initialisation; not a runtime credential.
No P1/P2 findings.

**AC-7 — Security review: network exposure — no P1/P2 findings**
Firewall rules (Terraform): inbound SSH (22) open to `0.0.0.0/0` (P3 only — SSH
key auth enforced, owner-only usage, no password auth). Inbound HTTP (80) and
HTTPS (443) open to all — required for Caddy and Let's Encrypt. All outbound
unrestricted. Internal services (orchestrator:8080, query:8081, telegram:8082,
dashboard:8084, postgres:5432, minio:9000/9001, observability stack) are Docker
network-only — confirmed via docker-compose.yml (no `ports:` mapping for internal
services). D-090 self-hosted runner eliminates inbound SSH from CI. No P1/P2
findings. P3 note: SSH to 0.0.0.0/0 is acceptable for a personal single-owner
system with key-only auth; can be tightened to a static owner IP if needed.

**AC-8 — All 29 in-scope blocks confirmed Done or formally gated; CI passes**
Block status as of v1.0:

| Block | Name | Status | Decision |
|---|---|---|---|
| 1 | Personality | Done | D-035, D-039, D-048 |
| 2 | Multi-Surface | Done | D-148 |
| 3 | UI/UX | Done | D-148 |
| 4 | Interface/Egress | Done | D-148 |
| 5 | Sync/State | Done | D-148 |
| 6 | Users | Done | D-145 |
| 7 | Trust Zones | Done | D-145 |
| 8 | Query/RAG | Done | D-130, D-133, D-142 |
| 9 | Action Layer | Done | D-133 |
| 10 | Workers | Done | D-142 |
| 11 | Memory | Done | D-130 |
| 12 | Context Window | Done | D-142 |
| 13 | Orchestrator | Done | D-094 |
| 14 | Ingestion | Done | D-104 |
| 15 | Processing | Done | D-104 |
| 16 | Storage | Done | D-094 |
| 17 | Tool Registry | Done | D-139 |
| 18 | Feedback | Done | D-110 |
| 19 | Config/Admin | Done | D-151 |
| 20 | Cost/Rate | Done | D-127 |
| 21 | Evolution Engine | Gated (post-v1) | D-042 |
| 22 | Alignment Layer | Done | D-037, D-060 |
| 23 | Telegram Surface | Done | D-094 |
| 24 | Sandboxing | Done (stub) | D-154 (this decision) |
| 25 | Observability | Done | D-124 |
| 26 | Physical Device | Gated (post-v1) | D-135 |
| 27 | Infrastructure | Done | D-094 |
| 28 | CI/CD | Done | D-094 |
| 29 | Documentation | Done | D-151 |

All 27 in-scope non-gated blocks are Done. Both gated blocks (21, 26) have
recorded decisions. No block is in an ambiguous partial state.

Unit tests for Block 24 stub: `src/sandboxing/tests/test_sandboxing_stub.py`
(10 tests). All pre-existing tests unchanged.

## Decision

CLIVE v1.0 is signed off. All eight acceptance criteria met.

**CLIVE v1 specification is complete.**

26 blocks Done. Block 24 Done (stub). Blocks 21 and 26 formally gated with
recorded decisions and explicit unblocking conditions.

## Unblocked by this decision

- **Block 21 (Evolution Engine):** Formally unblocked for v2. Prerequisites per
  D-042 are all satisfied: Blocks 17 (tool registry), 10 (workers), 6/7
  (users/zones), and 24 (sandboxing stub) are all Done. Owner decision required
  to activate.
- **Block 26 (Physical Device):** Formally unblocked for post-v1 when hardware
  readiness decision is made (D-135). Blocks 2 and 5 are Done.

## Related Decisions

- D-152 — v1.0 scope
- D-153 — v1.0 acceptance criteria
- D-042 — Block 21 paused (now unblocked for v2)
- D-135 — Block 26 gated (unblocking conditions stated)
- D-006 — Confirmation gate (preserved throughout)
- D-003 — Event bus (enforced throughout)
- D-004 — Alignment boundary (Block 22 owned by Architect throughout)
