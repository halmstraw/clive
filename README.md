# CLIVE

**Cognitive Living Intelligent Virtual Entity** — a personal AI system designed to know everything its owner knows, do everything its owner needs, and grow smarter over time.

CLIVE is not a chatbot. It is an ambient presence: persistent across sessions, opinionated, aligned, and built to evolve. Think JARVIS, not a wrapper around an API.

**Current version: v1.0** (signed off 17 May 2026, D-154)

---

## Contents

- [What CLIVE Is](#what-clive-is)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [User Guide](#user-guide)
- [Deployment](#deployment)
- [Development](#development)
- [Observability](#observability)
- [Decision Records](#decision-records)

---

## What CLIVE Is

CLIVE has three design ambitions:

**Know everything its owner knows.** Documents, notes, decisions, context — ingested, embedded, and retrievable. Every query draws on the owner's accumulated knowledge base plus full cross-session memory of past conversations.

**Do everything its owner needs.** Web search, reminders, document management, and background workers that run on schedule without being asked. Every action that writes, deletes, or sends goes through a confirmation gate — no autonomous irreversible action of any kind.

**Grow smarter without being asked.** A tool registry, background agents, and an evolution engine (gated for post-v1 activation) provide the substrate for self-improvement within a fixed alignment constitution. The system can optimise its means. It cannot rewrite its ends.

Two design philosophies underpin everything:

- **JARVIS** — a presence, not a chatbot. One coherent intelligence expressed across any surface.
- **The Hyperion Principle** — evolution within declared intent, never evolution of intent itself.

---

## Architecture

### The 38-Block Model

CLIVE is decomposed into 38 functional blocks, grouped by concern. Every block communicates exclusively through Block 13 (Central Orchestrator) via events — no block-to-block calls.

| Group | Blocks | Status |
|---|---|---|
| Experience | 1 Personality, 2 Multi-Surface, 3 UI/UX, 4 Interface/Egress, 5 Sync/State | Live |
| People & Access | 6 Users, 7 Trust Zones | Live |
| Intelligence | 8 Query/RAG, 9 Action Layer, 10 Workers, 11 Memory, 12 Context Window | Live |
| The Brain | 13 Orchestrator/Event Bus | Live |
| Knowledge | 14 Ingestion, 15 Processing, 16 Storage, 17 Tool Registry, 18 Feedback | Live |
| System Management | 19 Config/Admin, 20 Cost/Rate, 21 Evolution Engine, 22 Alignment Layer | Live (Block 21 gated) |
| Foundation | 23 Telegram Surface, 24 Sandboxing, 25 Observability, 26 Physical Device, 27 Infra/IaC, 28 CI/CD, 29 Documentation | Live (Blocks 24, 26 gated) |
| Business (v2+) | 30–38 | Out of v1 scope |

### Runtime Services

Five Python services run in Docker containers on a single Hetzner VM, coordinated by Block 13:

```
┌─────────────────────────────────────────────────────────────┐
│                        Hetzner VM (cx21)                    │
│                                                             │
│  ┌─────────────┐   ┌──────────────────────────────────────┐ │
│  │   Caddy     │   │            clive-internal network     │ │
│  │  (HTTPS)    │   │                                       │ │
│  └──────┬──────┘   │  ┌────────────┐  ┌────────────────┐  │ │
│         │          │  │ Orchestrat-│  │   Query/RAG    │  │ │
│   ┌─────▼──────┐   │  │ or (B13)   │◄─►  (B8)         │  │ │
│   │ Dashboard  │   │  │  :8080     │  │    :8081       │  │ │
│   │ (B2) :8084 │◄──┼──►            │  └────────────────┘  │ │
│   └────────────┘   │  │            │  ┌────────────────┐  │ │
│                    │  │            │◄─►  Telegram (B23)│  │ │
│   ┌────────────┐   │  │            │  │    :8082       │  │ │
│   │  Telegram  │   │  │            │  └────────────────┘  │ │
│   │    Cloud   │◄──┼──►            │  ┌────────────────┐  │ │
│   └────────────┘   │  │            │◄─►  Processing    │  │ │
│                    │  │            │  │  (B14/15):8083 │  │ │
│                    │  └─────┬──────┘  └────────────────┘  │ │
│                    │        │                              │ │
│                    │  ┌─────▼──────┐  ┌────────────────┐  │ │
│                    │  │ PostgreSQL  │  │    MinIO       │  │ │
│                    │  │ + pgvector  │  │  (raw store)   │  │ │
│                    │  └────────────┘  └────────────────┘  │ │
│                    └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Block 13 — Central Orchestrator** is the only service any other service calls directly. It runs an in-process pub/sub event bus, handles alignment gate checks on every event, routes actions through the confirmation gate (D-006), enforces tool registry permissions (D-131), and schedules background workers.

**Block 8 — Query/RAG** receives a query event from Block 13, assembles context (memory, knowledge chunks, tool availability, conversation history), calls the LLM via LiteLLM, and emits the response event.

**Block 23 — Telegram** is the primary user surface. It receives Telegram messages, authenticates by channel ownership (D-057), and emits structured events to Block 13. It also receives outbound events and renders them as Telegram messages.

**Block 14/15 — Processing** handles ingestion: receives a document, stores the raw file in MinIO, chunks it, embeds it via OpenAI, and writes searchable chunks to PostgreSQL/pgvector.

**Block 2 — Dashboard** is the second surface: a lightweight web application served by Caddy at the owner's domain, providing query, history, and pending action review.

### Storage Layout

PostgreSQL uses three schemas with role-based access:

| Schema | Purpose | DB Role |
|---|---|---|
| `clive_search` | Embedded chunks + pgvector index | `clive_app` |
| `clive_state` | System state: memory, tools, sessions, config, users, zones | `clive_app` |
| `clive_audit` | Append-only event log | `clive_audit_writer` (INSERT-only) |

MinIO holds raw ingested documents. rclone syncs them nightly to a separate Hetzner Object Storage bucket.

### Event Bus Principle (D-003)

No block communicates directly with another. All inter-block communication routes through Block 13 via typed events. This means Block 13 sees every interaction, can enforce alignment rules, log everything to the audit trail, and route dead letters without any block knowing about failures in another block.

### Alignment Layer (Block 22)

The alignment constitution is non-negotiable and owned exclusively by the system owner:

- CLIVE exists to serve its owner's genuine interests
- CLIVE does not act deceptively
- CLIVE does not take irreversible actions without explicit human confirmation
- CLIVE's goals are visible — no hidden optimisation targets
- CLIVE can refuse instructions that conflict with this constitution
- The Evolution Engine may optimise means. It may not modify these ends
- Personality (Block 1) survives the Evolution Engine — not subject to deprecation

Block 13 enforces this constitution on every event at dispatch time using deterministic rules and schema validation (no LLM-as-judge in v1, D-037).

---

## Technology Stack

| Component | Technology |
|---|---|
| Cloud | Hetzner (single VM, cx21) |
| Language | Python 3.12 |
| LLM | Anthropic Claude via LiteLLM (provider-agnostic) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO (S3-compatible) |
| IaC | Terraform (Hetzner provider) + Ansible |
| Containers | Docker Compose |
| CI/CD | GitHub Actions (self-hosted runner on the VM) |
| Primary Surface | Telegram bot |
| Second Surface | Web dashboard (FastAPI + Caddy + Let's Encrypt) |
| Observability | Grafana Alloy → Grafana Cloud (metrics + logs) |
| Search | Brave Search API or SerpAPI (configurable) |

---

## User Guide

### Talking to CLIVE

Send any message to the Telegram bot. CLIVE has access to:
- Your full knowledge base (everything you have ingested)
- Cross-session memory (entities, facts, and summaries from past conversations)
- Web search (triggered automatically on search-intent queries)
- Reminders (set by saying "remind me to..." or "remind me about...")

CLIVE's default stance is concise, direct, and honest. It will push back on bad ideas and volunteer its assessment on high-stakes matters without being asked.

### Telegram Commands

| Command | What it does |
|---|---|
| `/help` | List all available commands |
| `/ingest` | Ingest a document sent from desktop (caption the file with `/ingest`) |
| `/list` | List all ingested documents |
| `/delete <filename>` | Request deletion of a document (requires confirmation) |
| `/confirm_delete` | Confirm a pending deletion |
| `/cancel_delete` | Cancel a pending deletion |
| `/bad` | Mark the most recent response as poor quality (Block 18 feedback) |
| `/status` | System status: cost today, daily cap, memory stats, tool count |
| `/tools` | List all registered tools and their enabled/disabled state |
| `/tool_disable <name>` | Disable a tool (requires confirmation) |
| `/tool_enable <name>` | Enable a tool (requires confirmation) |
| `/confirm_action` | Confirm a pending action (web search, reminder, tool change) |
| `/cancel_action` | Cancel a pending action |
| `/whoami` | Show your user profile and zone access |

### Document Ingestion

**From desktop:** Attach a file to a Telegram message and set the caption to `/ingest`. CLIVE will acknowledge, process, and confirm ingestion.

**From mobile:** Send the document without a caption. CLIVE will ask you to confirm with `/ingest_confirm`. Send that command to proceed.

Supported formats: any file up to 10 MB. Text extraction handles PDF, plain text, and common document formats. Larger files are rejected with an explanation.

### Actions Requiring Confirmation

Any action that is irreversible — deletion, web search (which sends a query externally), reminders, tool state changes — requires explicit confirmation:

1. CLIVE proposes the action and shows what it will do
2. You send `/confirm_action` or `/cancel_action`
3. CLIVE executes or discards accordingly

This is enforced at the architecture level (D-006). No autonomous irreversible action is possible.

### Web Dashboard

The dashboard is available at your configured domain (behind Caddy with Let's Encrypt TLS). It provides:
- Query interface with the same backend as Telegram
- Conversation history shared across Telegram and the dashboard
- Pending action review and confirmation
- Session authentication via a configurable dashboard secret

---

## Deployment

### Prerequisites

- Hetzner Cloud account with API access and Object Storage enabled
- GitHub repository with Actions enabled
- Telegram bot token (create via BotFather)
- Anthropic API key
- OpenAI API key (for embeddings)
- Search API key (Brave or SerpAPI)
- SSH key pair

### 1. Bootstrap Terraform State

See `docs/runbooks/terraform-bootstrap.md` for the full procedure. In summary:

1. Create a Hetzner Object Storage bucket named `clive-terraform-state` in `fsn1`
2. Create an Object Storage access key pair
3. Configure `infrastructure/terraform/terraform.tfvars` from the example file
4. Run `terraform init` and `terraform plan` to verify connectivity
5. Populate GitHub Actions secrets (see the runbook for the full list)

### 2. Provision the VM

```bash
cd infrastructure/terraform
terraform apply
```

Copy the output `clive_server_ip` and add it as the `CLIVE_SERVER_IP` GitHub Actions secret.

### 3. Configure the VM

```bash
ansible-playbook -i infrastructure/ansible/inventory \
  infrastructure/ansible/playbook.yml \
  --ask-vault-pass
```

This installs Docker, configures secrets, deploys the Compose stack, initialises PostgreSQL, sets up nightly backups, and registers the self-hosted GitHub Actions runner.

### 4. Required GitHub Actions Secrets

| Secret | Description |
|---|---|
| `HCLOUD_TOKEN` | Hetzner Cloud API token |
| `CLIVE_SSH_PRIVATE_KEY` | SSH private key for the VM |
| `CLIVE_SSH_PUBLIC_KEY` | Matching SSH public key |
| `CLIVE_SERVER_IP` | VM IP (available after terraform apply) |
| `OWNER_IP` | Your IP for SSH firewall allow-rule |
| `TF_STATE_ACCESS_KEY` | Hetzner Object Storage key for Terraform state |
| `TF_STATE_SECRET_KEY` | Hetzner Object Storage secret for Terraform state |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_OWNER_CHAT_ID` | Your Telegram chat ID |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key (embeddings) |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password |
| `APP_DB_PASSWORD` | `clive_app` role password |
| `AUDIT_WRITER_PASSWORD` | `clive_audit_writer` role password |
| `MINIO_ROOT_USER` | MinIO root username |
| `MINIO_ROOT_PASSWORD` | MinIO root password |
| `SEARCH_API_KEY` | Brave or SerpAPI key |
| `DASHBOARD_SECRET` | Web dashboard session secret |
| `GRAFANA_CLOUD_PROMETHEUS_URL` | Grafana Cloud remote_write endpoint |
| `GRAFANA_CLOUD_PROMETHEUS_USER` | Grafana Cloud metrics user ID |
| `GRAFANA_CLOUD_LOKI_URL` | Grafana Cloud Loki push endpoint |
| `GRAFANA_CLOUD_LOKI_USER` | Grafana Cloud Loki user ID |
| `GRAFANA_CLOUD_API_KEY` | Grafana Cloud API key (MetricsPublisher + LogsPublisher) |

### 5. Activate System Documents

After the first deploy, the personality and alignment rules documents are seeded but inactive. Activate them via Telegram:

```
/activate personality
# Review the preview, then:
/confirm_activate <version_id>

/activate alignment_rules
# Review the preview, then:
/confirm_activate <version_id>
```

Both must be activated before CLIVE responds with its personality.

### 6. Verify

Send a test message to the bot. CLIVE should respond with its personality active. Check `/status` to confirm cost tracking and memory are live.

### CI/CD Pipeline

Push to `main` triggers the full pipeline:

1. **CI** (`ci.yml`) — runs on `ubuntu-latest`: Terraform fmt/validate, Ansible lint, Compose dry-run, SQL idempotency tests, unit tests for all services (90% coverage minimum), DB role privilege tests
2. **Deploy** (`deploy.yml`) — runs on the self-hosted runner: builds and pushes Docker images to GHCR, writes the secrets file, applies DB migrations, deploys updated containers, runs health checks
3. **Rollback** (`rollback.yml`) — triggered automatically if verify fails; reverts to the previous image tags

Terraform changes (`terraform.yml`) run plan automatically on PR and require manual apply. Ansible changes (`ansible.yml`) are applied via a separate workflow with explicit approval.

---

## Development

### Local Setup

```bash
# Each service is an independent Python package
cd src/orchestrator
pip install -e ".[dev]"
python -m pytest tests/ -v

cd src/query
pip install -e ".[dev]"
python -m pytest tests/ -v

# etc. for telegram, processing, dashboard
```

### Environment Variables

All secrets come from `/etc/clive/secrets.env` in production (Ansible-injected). For local development, copy `infrastructure/compose/.env.example` to `.env` and create a local `secrets.env`.

Never commit real secret values. The CI pipeline creates a stub secrets file from the example file (D-084).

### Testing

Tests must pass before any deploy. The CI pipeline enforces:

- **Unit tests** for all five Python services with 90% coverage minimum (D-155)
- **SQL idempotency tests** — every init script runs twice, errors on second run fail the build
- **Database role privilege tests** — assert `clive_audit_writer` cannot UPDATE or DELETE, `clive_app` cannot write to the audit log, etc.
- **Compose dry-run** — validates the full Compose configuration parses correctly

Run the full test suite locally before pushing:

```bash
# From each service directory:
python -m pytest tests/ -v --cov=<module> --cov-fail-under=90
```

### Adding a Document to CLIVE's Knowledge

Send a file to the Telegram bot using the ingest commands above, or add ingestion programmatically by posting to the orchestrator's `/ingest` endpoint with appropriate auth metadata.

### Adding a New Tool/Action

1. Add a row to the `tool_registry` table (or use the `/tool_enable` flow via Telegram)
2. Implement the handler in Block 9 (`src/orchestrator/orchestrator/handlers/`)
3. Register it with Block 13's event router
4. All tool actions must pass through the confirmation gate (D-006)

---

## Observability

CLIVE ships full observability via Grafana Cloud:

- **Metrics** — Prometheus-format metrics from all services, scraped by Grafana Alloy and shipped to Grafana Cloud remote_write
- **Logs** — Structured JSON logs from all containers, collected by Alloy and shipped to Grafana Cloud Loki
- **Event bus** — Every event dispatched by Block 13 is logged as a structured JSON line, with a dedicated Grafana dashboard
- **Host metrics** — node_exporter for VM CPU/memory/disk; postgres-exporter for database metrics
- **Alerts** — Configured in Grafana Cloud UI; alert webhooks route to Block 13, which delivers them to the owner via Telegram (D-118)

The `/status` Telegram command provides a quick summary without needing Grafana:
- LLM spend today vs daily cap
- Query and action counts
- Memory entity count
- Active tool count
- System health indicators

See `docs/runbooks/observability.md` for Grafana dashboard setup and alert configuration.

---

## Decision Records

Every significant architectural decision is recorded as an ADR in `docs/decisions/` and indexed in `DECISIONS.md`. Git history is the audit trail. The index is the single source of truth.

**Highest decision ID:** D-157

Key decisions for orientation:

| ID | Decision |
|---|---|
| D-001 | CLIVE is a single-owner system |
| D-003 | All inter-block communication via Block 13 event bus |
| D-004 | Alignment Layer governs the goal function; Evolution Engine may not modify ends |
| D-005 | Personality (Block 1) survives the Reaper |
| D-006 | Every irreversible action requires explicit human confirmation |
| D-057 | Authentication is channel-as-authentication (Telegram owner chat ID) |
| D-064 | Single cloud VM (Hetzner cx21) |
| D-065 | PostgreSQL + pgvector for the search index |
| D-077 | LLM calls via LiteLLM (Anthropic by default; provider-agnostic) |
| D-154 | CLIVE v1.0 signed off (17 May 2026) |

---

## What's Gated for Post-v1

Two blocks are explicitly gated pending post-v1 decisions:

**Block 21 — Evolution Engine:** The substrate is ready (Tool Registry, Workers, Users/Zones, Sandboxing stub). Activation requires an explicit owner decision. The evolution engine can mutate means; alignment constitution changes require owner sign-off per promotion (D-034).

**Block 26 — Physical Device / Edge Node:** Gated pending Blocks 2 and 5 maturing and a hardware readiness decision (D-135).

**Blocks 30–38 — Business Layer:** Out of v1 scope per D-036.

---

*CLIVE — personal AI system. v1.0. Built May 2026.*
