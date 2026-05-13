*Infrastructure Agent artefact — produced May 2026. Complete. All technology choices resolved. Ready for implementation.*

---
# Block 27 / 28 — IaC & CI/CD Specification (Infrastructure Agent)

**Status:** Complete. Produced by the Infrastructure Agent, May 2026. All technology choices resolved (D-064 through D-075). Ready for implementation.

---

## Decisions This Artefact Implements

| Decision | Summary |
|---|---|
| D-064 | Single cloud VM for all v0.1 services |
| D-070 | Hetzner as cloud provider |
| D-071 | Terraform as IaC provisioning tool |
| D-072 | Docker Compose + Ansible for container and VM management |
| D-074 | No staging environment; direct to production |
| D-075 | GitHub Actions as CI/CD pipeline tool |
| D-056 | 24-hour max data loss window; nightly snapshot |
| D-069 | Separate backup required for S3 object store |

---

## Repository Structure

```
infrastructure/
  terraform/
    main.tf                    # VM, firewall, Hetzner backup, remote state bucket
    variables.tf
    outputs.tf
    terraform.tfvars.example   # committed; actual tfvars gitignored
  ansible/
    playbook.yml
    inventory.example          # committed; actual inventory gitignored
    roles/
      base/                    # OS hardening, fail2ban, unattended upgrades
      docker/                  # Docker + Docker Compose install
      clive-secrets/           # Secrets injection (Telegram token, DB creds, MinIO creds)
      postgres-init/           # Schema and role initialisation (idempotent SQL)
      backup-cron/             # Nightly object store backup job
  compose/
    docker-compose.yml         # All v0.1 services
    .env.example               # committed; actual .env gitignored
  sql/
    init/
      01_extensions.sql        # CREATE EXTENSION IF NOT EXISTS vector
      02_schemas.sql           # clive_search, clive_state, clive_audit
      03_roles.sql             # clive_app, clive_audit_writer
      04_audit_table.sql       # Append-only audit table definition

.github/
  workflows/
    ci.yml                     # Lint + test on every push
    deploy.yml                 # Build + deploy + verify on main
    rollback.yml               # Manual trigger rollback
```

---

## Block 27 — Terraform

### VM specification

- Provider: Hetzner Cloud (`hetznercloud/hcloud`)
- VM type: CX21 (2 vCPU, 4 GB RAM) or equivalent — sufficient for v0.1 single-surface query-only load
- OS: Ubuntu 24 LTS
- Region: European datacentre (nbg1 or fsn1)
- SSH key registered at provisioning time; root password login disabled
- Firewall rules: inbound SSH restricted to owner IP only; no inbound HTTP/HTTPS (Telegram bot uses outbound only); all other inbound blocked
- Hetzner automated backup enabled on the VM resource — satisfies D-056 nightly snapshot requirement with one resource attribute
- Output: VM public IP address for Ansible inventory

### Remote state

Terraform state stored in a Hetzner S3-compatible object storage bucket (or equivalent). State locking enabled via the remote backend. **This bucket must be created and configured before the first `terraform apply` — it is a bootstrap prerequisite, not managed by Terraform itself.**

State files and `.tfvars` are gitignored. Only `.tfvars.example` with empty variable declarations is committed.

---

## Block 27 — Ansible

### `base` role

- `apt upgrade` and unattended-upgrades configuration
- `fail2ban` install and SSH jail configuration
- `ufw` firewall rules matching Terraform firewall (defence in depth)
- NTP configuration
- Creation of dedicated non-root `clive` service user; Docker group membership

### `docker` role

- Docker Engine install (official Docker apt repository)
- Docker Compose plugin install
- Docker daemon configuration (log rotation, default network settings)

### `clive-secrets` role

- Writes secrets file to `/etc/clive/secrets.env`, owned by `clive`, mode 0600
- Variables injected at deploy time via Ansible vault or environment variables — never committed
- Secrets at v0.1: `TELEGRAM_BOT_TOKEN`, `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
- `.env.example` in repo shows required variable names with no values

### `postgres-init` role

- Runs SQL init scripts from `sql/init/` against the PostgreSQL container on first deploy
- Scripts are idempotent (`CREATE IF NOT EXISTS`, `DO $$ IF NOT EXISTS $$` patterns)
- Confirms pgvector extension is loaded, all schemas exist, all roles exist with correct privileges
- Role `clive_app`: CONNECT + USAGE on `clive_search` and `clive_state` schemas; INSERT-only on `clive_audit`
- Role `clive_audit_writer`: INSERT-only on audit table; no other privileges

### `backup-cron` role

- Installs and configures a nightly cron job (or systemd timer) running as the `clive` user
- Job: sync MinIO data volume to a separate Hetzner storage volume or object storage bucket using `rclone sync` or `mc mirror`
- Runs at 02:00 local time, after the Hetzner VM snapshot window
- Job outcome (success/failure) logged to `/var/log/clive-backup.log`
- Both PostgreSQL (via Hetzner VM snapshot) and MinIO (via this cron) are recoverable to the same 24-hour window per D-056 and D-069

---

## Block 27 — Docker Compose

### Services

**`orchestrator` (Block 13)**

- Long-running containerised service per D-063
- In-process pub/sub event bus per D-062; no external broker
- Restart policy: `always`
- Health check: HTTP endpoint responding on internal port
- Environment: references secrets file via `env_file: /etc/clive/secrets.env`
- Named volume mount: `/data/clive` for event log persistence

**`postgres` (Block 16 — search index, state store, audit log)**

- PostgreSQL with pgvector extension (D-065, D-066, D-067)
- Restart policy: `always`
- Named volume: `postgres_data`
- `listen_addresses` scoped to container network only (not exposed on host)
- Init scripts mounted from `sql/init/` — run once on first start
- Health check: `pg_isready`

**`minio` (Block 16 — raw store)**

- S3-compatible object storage per D-068
- Restart policy: `always`
- Named volume: `minio_data`
- Console port not exposed externally; API port scoped to container network
- Health check: MinIO healthcheck endpoint
- Note: when Hetzner native object storage or another S3-compatible provider is preferred, only the endpoint and credentials change — application code is unaffected

**`backup` (sidecar)**

- Runs nightly object store sync per D-069
- Lightweight container with `rclone` or MinIO client (`mc`)
- Triggered by `backup-cron` Ansible role; not a long-running service
- Restart policy: `no`

### Secrets pattern

All secrets referenced via `env_file` pointing to `/etc/clive/secrets.env`. This file is injected by Ansible and never present in the repository. `.env.example` in `compose/` lists required variable names with placeholder values and is committed.

---

## Block 25 — Observability Requirements

### What Block 25 must do

**Logging** — Subscribes to the full event stream via Block 13. Persists structured log records to Block 16. Every log record carries: timestamp, block ID, event type, event ID, conversation ID (where applicable), zone scope, outcome. Sensitive payload content (message text, personal knowledge chunks) is redacted; metadata is preserved.

**Tracing** — Reconstructs end-to-end traces for any query, action request, or worker run using correlation IDs propagated across event hops. A trace shows: events fired, order, outcomes, and step latency.

**Metrics** — Derived from event stream at v0.1: query latency (Telegram receipt to response delivery), retrieval success rate, event delivery success rate (retry outcomes per D-055), dead-letter event count, token consumption per query.

**Alerting** — Evaluates incoming events against alert rules; emits `alert.triggered` events to Block 13 when thresholds breached. Routes to Block 4 for delivery to owner. Alert conditions at v0.1: dead-letter event logged; query error rate above threshold; token budget approaching limit; Block 13 retry exhaustion triggered. Alert payload schema per D-073 placeholder (jointly owned with Block 4 per D-059).

**Evolution history view** — Ingests bridge-origin `evolution_history` events from Block 21 (D-032). Stores and surfaces these with provenance metadata flagged as experimental-origin. Owner can see that a record originated from the experimental zone.

**Owner-facing view** — At v0.1: queryable interface via Block 8 / Block 13 (D-043 pattern). Owner asks CLIVE about system state; Block 8 retrieves from Block 25's stored records. Visual dashboard deferred to post-v0.1.

### Experimental environment observability

Block 25 does not extend into the experimental environment (D-032). The experimental environment has its own separate, minimal lightweight observability capability: structured logging and a retained event store scoped to the experimental zone. Its only production-visible output is the standardised `evolution_history` event type, which crosses the bridge and passes the enhanced alignment gate (D-030) before Block 25 ingests it.

### What Block 25 must not do

- Deploy into or connect to experimental infrastructure (D-032)
- Create a second cross-environment channel (D-022)
- Store unredacted sensitive personal content in log records
- Emit alerts that bypass Block 13 and reach Block 4 directly (D-003)
- Take any write action without routing through Block 9 confirmation gate — Block 25 is read/observe only

### Interfaces

Block 25 subscribes to the full event stream via Block 13. It emits:

- `alert.triggered` — carries the D-073 placeholder alert payload schema
- `evolution_history.received` — when a bridge-origin evolution event is ingested and stored

Block 25 exposes a retrieval interface to Block 8 (via Block 13, D-043 pattern) for owner observability queries.

---

## Block 28 — CI/CD Pipeline

### Tool

GitHub Actions (D-075). Pipeline definitions live in `.github/workflows/`.

### `ci.yml` — Every push

Runs in parallel where possible:

1. **lint-validate**
   - `terraform validate` + `terraform fmt --check`
   - `ansible-lint` on all playbook files
   - `docker compose config` dry-run
   - Application code linter
   - Fails pipeline on any violation

2. **test**
   - Unit tests for application code
   - Schema migration dry-run: run `sql/init/` scripts against a temporary PostgreSQL container; confirm idempotent success
   - Pipeline does not fail on zero tests; fails on test failures

### `deploy.yml` — Main branch only (after ci passes)

1. **build**
   - Docker image build for Block 13 orchestrator (and each subsequent block as implemented)
   - Images tagged with git SHA
   - Images pushed to container registry (Docker Hub or GitHub Container Registry — implementation detail)

2. **deploy**
   - SSH to Hetzner VM
   - `docker compose up -d --pull always` with new image tags
   - Ansible playbook re-run if files under `ansible/` have changed (path filter)
   - `terraform plan` + `terraform apply` if files under `terraform/` have changed (path filter)
   - System document changes (personality, alignment rules): delivered to Block 16 with status `pending_activation`; owner confirms activation via Telegram separately per D-049. **Pipeline never auto-activates system documents.**

3. **verify**
   - `docker compose ps` — confirm all containers running
   - Block 13 health endpoint responds
   - PostgreSQL `pg_isready` responds
   - If verify fails: trigger rollback automatically

### `rollback.yml` — Manual trigger or auto-triggered by verify failure

1. **rollback**
   - Re-deploy previous git SHA's image tags
   - Same `docker compose up -d` mechanism with prior tag
   - Rollback logged as a deployment event to Block 13 / Block 25
   - Owner notified via Block 4 (Telegram)

### Audit trail

Every pipeline run logged natively by GitHub Actions (actor, SHA, branch, stage outcomes, timestamps). Significant deployment events (successful deploy, failed deploy, rollback triggered) additionally emitted as events to Block 13 / Block 25 as part of the deploy stage — visible in CLIVE's own observability view.

### Secrets management in pipeline

- Hetzner API token, SSH private key, container registry credentials stored as GitHub Actions secrets
- Ansible vault password or secrets values passed as masked environment variables
- No secrets in repository files at any path

---

## Alert Payload Schema (D-073 Placeholder)

Jointly owned by Block 25 and Block 4 per D-059. Held by Architect pending Experience Agent review.

| Field | Type | Notes |
|---|---|---|
| `alert_id` | uuid | Unique per alert |
| `alert_type` | string (enum) | `capacity_backpressure`, `dead_letter`, `query_error_rate`, `token_budget_warning` |
| `severity` | string (enum) | `info`, `warn`, `error` |
| `title` | string | Short human-readable summary |
| `body` | string | Full detail |
| `source_block` | integer | Originating block number |
| `timestamp` | ISO8601 | |
| `conversation_id` | uuid or null | Present if alert is conversation-scoped |

Experience Agent must review and adopt or revise this schema in its first session. Any revision requires a superseding decision entry and acknowledgement from both the Infrastructure Agent and Experience Agent per D-059.

---

## Open Items for Next Session

1. **Write actual files.** This artefact is a specification. The next Infrastructure Agent session produces the actual Terraform, Ansible, Compose, SQL, and GitHub Actions files.
2. **Terraform state bucket bootstrap runbook (D-076).** The remote state bucket must exist before the first `terraform apply`. This is a manual one-time step. The Infrastructure Agent must produce a runbook entry for Block 29 (Documentation) covering: how to create the bucket, configure the Terraform backend, and verify state locking before any apply is attempted. Block 29 owns the runbook; the Infrastructure Agent produces the content.
3. **Experience Agent review of alert schema** (D-073) — required before Block 25 implementation is considered final.

---

*Infrastructure Agent artefact — produced May 2026*
*Covers: Block 25 (Observability requirements), Block 27 (IaC specification), Block 28 (CI/CD specification)*
