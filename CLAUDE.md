## [CLAUDE.md](http://CLAUDE.md)

# CLIVE — Claude Code Workspace

## What this repository is

CLIVE is a personal AI system built for a single owner. This repository
contains all infrastructure definitions and application source code.

All design decisions are recorded in Notion. All implementation follows
the specifications in Notion artefacts. Claude Code's job is to write
code that faithfully implements those specifications — not to make design
decisions.

## Repository structure

```

infrastructure/

terraform/        # Hetzner VM provisioning (Terraform)

ansible/          # VM configuration (Ansible)

compose/          # Container orchestration (Docker Compose)

sql/init/         # PostgreSQL schema initialisation

.github/workflows/  # CI/CD pipelines (GitHub Actions)

src/

orchestrator/     # Block 13 — Central Orchestrator

query/            # Block 8 — Query / RAG service

telegram/         # Block 23 — Telegram surface

docs/

runbooks/         # Operational runbooks

```

## Technology stack

- Cloud: Hetzner (single VM, cx21)
- IaC: Terraform + Ansible + Docker Compose
- CI/CD: GitHub Actions
- Database: PostgreSQL 16 + pgvector
- Object storage: MinIO (S3-compatible)
- Language: Python 3.12
- LLM: LiteLLM (default: Anthropic Claude)
- Surface: Telegram bot

## Key constraints — read before writing any code

1. **No direct block-to-block calls.** All inter-service communication
   routes through the Block 13 orchestrator. Services communicate via
   HTTP to Block 13's event intake endpoint, not to each other directly.

2. **Audit log is immutable.** The `clive_audit_writer` PostgreSQL role
   has INSERT-only privileges. Never grant UPDATE or DELETE on the audit
   table.

3. **Secrets are never in code or committed files.** All secrets come
   from `/etc/clive/secrets.env` injected by Ansible. Use `env_file`
   in Compose and `load_dotenv('/etc/clive/secrets.env')` in Python.

4. **System documents (personality, alignment rules) are never
   auto-activated.** Loading a new version into Block 16 sets
   `is_active = false`. Activation is a separate explicit owner action.

5. **All SQL init scripts must be idempotent.** Use `CREATE IF NOT EXISTS`,
   `ON CONFLICT DO NOTHING`, and `DO $$ IF NOT EXISTS $$` patterns.

6. **Tests must pass before any deploy.** The CI pipeline (`ci.yml`)
   runs SQL idempotency tests and unit tests. Do not bypass.

## Notion artefacts — implementation source of truth

All implementation specifications live in Notion. When implementing,
read the relevant artefact first. Do not deviate from the specification
without flagging it.

| Artefact | Notion URL | Content |
|---|---|---|
| Infrastructure files | https://www.notion.so/3584837a97d3818899eaf3af8ec111be | Terraform, Ansible, Compose, SQL, GitHub Actions |
| Block 13 orchestrator | https://www.notion.so/3584837a97d3818fbc02f885155fd234 | Python orchestrator service |
| Block 8 query service | https://www.notion.so/3584837a97d3818e8c31cc7dec57fb22 | Python query/RAG service |
| Block 23 Telegram surface | https://www.notion.so/3584837a97d381adae5bf2a16e77deb2 | Python Telegram bot |
| Block 13 requirements | https://www.notion.so/3574837a97d3812d82a8c8873fa3bf51 | Full orchestrator requirements |
| Block 16 requirements | https://www.notion.so/3584837a97d3810dac6eded7ef383068 | Full storage requirements |
| Block 8 requirements | https://www.notion.so/3584837a97d381a18d71c239ed9dd3d7 | Full query requirements |
| Block 23 requirements | https://www.notion.so/3584837a97d3818a979ef3e24706bf56 | Full surface requirements |
| IaC specification | https://www.notion.so/3584837a97d381b0915fd8b5cf71ea54 | Block 27/28 spec |
| Bootstrap runbook | In infrastructure files artefact | Terraform state setup |

## Decisions log

All architectural decisions are in DECISIONS.md, maintained live in Notion:
https://www.notion.so/3574837a97d381568100cd1370c68264

Highest decision ID at time of writing: D-089.

If implementation reveals a gap or conflict not covered by existing
decisions, stop and flag it. Do not resolve design questions in code.

## Commit conventions

```

feat: <description>     # New capability

fix: <description>      # Bug fix

chore: <description>    # Infrastructure, tooling, config

docs: <description>     # Documentation only

test: <description>     # Tests only

```

Commit one logical unit at a time. Do not bundle infrastructure and
application code in the same commit.

## Environment variables

All secrets are in `/etc/clive/secrets.env` (production, Ansible-injected).
For local development, copy `.env.example` to `.env` and fill in values.
Never commit `.env` or any file containing real secret values.

Required secrets for v0.1:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_OWNER_CHAT_ID`
- `ANTHROPIC_API_KEY`
- `AUDIT_WRITER_PASSWORD`
- `APP_DB_PASSWORD`
- `POSTGRES_PASSWORD`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`

## Pre-launch checklist

Before first deploy:
- [ ] Terraform state bucket bootstrapped (see `docs/runbooks/terraform-bootstrap.md`)
- [ ] All GitHub Actions secrets populated
- [ ] Telegram bot created via BotFather — token saved
- [ ] Owner chat ID obtained via @userinfobot — saved
- [ ] Anthropic API key obtained — saved
- [ ] PostgreSQL passwords chosen and saved
- [ ] MinIO credentials chosen and saved
- [ ] `terraform apply` completed, VM IP recorded
- [ ] Ansible playbook run against VM
- [ ] `docker compose up` on VM, all containers healthy
- [ ] Personality document loaded into Block 16 and activated
- [ ] Alignment rules document loaded into Block 16 and activated
- [ ] At least one knowledge document ingested
- [ ] First message sent to CLIVE via Telegram
