# CLIVE — Claude Code Workspace

> This file is read automatically by Claude Code at every session start.
> It is the ground truth for session context, constraints, and orientation.
> Do not delete or move it. Update it only via a recorded decision.

---

## What CLIVE Is

CLIVE (Cognitive Living Intelligent Virtual Entity) is a personal AI system
designed to know everything its owner knows, do everything its owner needs,
and grow smarter over time without being asked to. It is ambient, persistent,
and aligned. It has a personality. It evolves.

Design philosophy: JARVIS (presence, not chatbot) + the Hyperion Principle
(evolution within fixed intent, never evolution of intent itself).

---

## Repo Structure

```
/
├── CLAUDE.md                    ← this file
├── .claude/
│   ├── agents/                  ← specialist subagent definitions
│   │   ├── architect.md
│   │   ├── systems-agent.md
│   │   ├── infrastructure-agent.md
│   │   ├── intelligence-agent.md
│   │   ├── knowledge-agent.md
│   │   ├── access-security-agent.md
│   │   └── experience-agent.md
│   └── skills/                  ← reusable workflow skills
│       ├── fetch-decisions/SKILL.md
│       ├── record-decision/SKILL.md
│       ├── event-schema/SKILL.md
│       └── requirements-output/SKILL.md
├── infrastructure/
│   ├── terraform/               # Hetzner VM provisioning
│   ├── ansible/                 # VM configuration
│   ├── compose/                 # Container orchestration (Docker Compose)
│   └── sql/init/                # PostgreSQL schema initialisation
├── .github/workflows/           # CI/CD pipelines (GitHub Actions)
├── src/
│   ├── orchestrator/            # Block 13 — Central Orchestrator
│   ├── query/                   # Block 8 — Query / RAG service
│   └── telegram/                # Block 23 — Telegram surface
└── docs/
    ├── runbooks/                # Operational runbooks
    ├── spec/
    │   └── clive-v0.1.md        # CLIVE specification (local copy for reference)
    └── requirements/            # Block requirements documents
```

---

## Technology Stack

- Cloud: Hetzner (single VM, cx21)
- IaC: Terraform + Ansible + Docker Compose
- CI/CD: GitHub Actions
- Database: PostgreSQL 16 + pgvector
- Object storage: MinIO (S3-compatible)
- Language: Python 3.12
- LLM: LiteLLM (default: Anthropic Claude)
- Surface: Telegram bot

---

## The 38 Blocks — Quick Reference

| Group | Blocks |
|---|---|
| Experience | 1 Personality, 2 Multi-Surface, 3 UI/UX, 4 Interface/Egress, 5 Sync/State |
| People & Access | 6 Users, 7 Trust Zones |
| Intelligence | 8 Query/RAG, 9 Action Layer, 10 Workers, 11 Memory, 12 Context Window |
| The Brain | 13 Orchestrator/Event Bus |
| Knowledge | 14 Ingestion, 15 Processing, 16 Storage, 17 Tool Registry, 18 Feedback |
| System Management | 19 Config/Admin, 20 Cost/Rate, 21 Evolution Engine, 22 Alignment Layer |
| Foundation | 23 Security, 24 Sandboxing, 25 Observability, 26 Physical Device, 27 Infra/IaC, 28 CI/CD, 29 Documentation |
| Business (v2+) | 30–38 — out of v1 scope per D-036 |

---

## Agent Roster

| Agent | Blocks | Status |
|---|---|---|
| Architect | 22 (owns) + system-wide review | Active |
| Systems Agent | 13, 19, 20, 21 | Active (Block 21 paused) |
| Infrastructure Agent | 25, 26, 27, 28, 29 | Active |
| Intelligence Agent | 8, 9, 10, 11, 12 | Active — Block 8 first |
| Knowledge Agent | 14, 15, 16, 17, 18 | Active — Block 16 first |
| Access & Security Agent | 6, 7, 23, 24 | Not yet activated |
| Experience Agent | 1, 2, 3, 4, 5 | Not yet activated |
| Business Agent | 30–38 | Out of v1 scope |

Agents are defined as subagent files in `.claude/agents/`.
The Architect orchestrates. Specialists execute within their block group.
The owner approves decisions. The owner is the only person who can modify
the alignment constitution.

---

## Authoritative Sources — Fetch Before Acting

Implementation specifications live in Notion. Decisions live in the repo.
Do not treat any local Notion copy as authoritative for decisions.

| Artefact | Location | When to load |
|---|---|---|
| DECISIONS.md | `DECISIONS.md` (repo root) — read locally | Every session start |
| Agent Prompts Index | https://www.notion.so/3584837a97d38119b056f70c58da5e62 | When activating a specialist |
| Architect Prompt | https://www.notion.so/3584837a97d38172a609ecbcae152ac4 | Architect sessions |
| Systems Agent Prompt | https://www.notion.so/3584837a97d3812bb22fc98048103b6c | Systems work |
| Infrastructure Agent Prompt | https://www.notion.so/3584837a97d3816f9af7d64ebd37754e | Infra work |
| Intelligence Agent Prompt | https://www.notion.so/3584837a97d381cbb91fe5096e093743 | Intelligence work |
| Knowledge Agent Prompt | https://www.notion.so/3584837a97d381c6ab74c81f57a936a0 | Knowledge work |
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

---

## Non-Negotiable Constraints

These apply to every agent, every session, every output.
They are not suggestions. Violation requires immediate correction.

**D-003 — Event Bus**
No block communicates directly with another block.
All inter-block communication routes through Block 13 (Central Orchestrator) via events.
Any design introducing a direct block-to-block call is wrong. Redesign it.

**D-004 — Alignment Boundary**
Block 22 (Alignment Layer) is owned by the Architect, not specialists.
No agent modifies the alignment constitution. Only the owner can.
When a design touches alignment constraints, route to Architect before proceeding.

**D-005 — Personality Survives the Reaper**
Block 1 (Personality) is not subject to the Evolution Engine or the Reaper.
Do not design evolution mechanisms that target personality parameters.

**D-006 — Confirmation Gate**
Any capability that can write, delete, send, or take irreversible action
must route through Block 9 (Action Layer) confirmation gate.
No autonomous irreversible action of any kind.

**D-002 — No Technology Choices in Requirements**
Requirements describe what a block must do and what constraints it must satisfy.
Technology decisions come later. Do not name specific technologies in requirements work.

**Implementation constraints**
- The `clive_audit_writer` PostgreSQL role has INSERT-only privileges. Never grant UPDATE or DELETE on the audit table.
- Secrets are never in code or committed files. All secrets come from `/etc/clive/secrets.env` injected by Ansible. Use `env_file` in Compose and `load_dotenv('/etc/clive/secrets.env')` in Python.
- System documents (personality, alignment rules) are never auto-activated. Loading a new version into Block 16 sets `is_active = false`. Activation is a separate explicit owner action.
- All SQL init scripts must be idempotent. Use `CREATE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, and `DO $$ IF NOT EXISTS $$` patterns.
- Tests must pass before any deploy. The CI pipeline (`ci.yml`) runs SQL idempotency tests and unit tests. Do not bypass.

---

## Alignment Constitution (Block 22 — Current State)

- CLIVE exists to serve its owner's genuine interests.
- CLIVE does not act deceptively.
- CLIVE does not take irreversible actions without explicit human confirmation.
- CLIVE's goals are visible. It has no hidden optimisation targets.
- CLIVE can refuse instructions that conflict with this constitution.
- The Evolution Engine may optimise means. It may not modify these ends.
- Personality (Block 1) survives the Reaper. It is not subject to evolutionary deprecation.

This constitution may only be changed by the owner.
Any change must be recorded in DECISIONS.md before taking effect.

---

## Decision Protocol

Every agent uses this format for every ask to the owner. One ask per message.

```
AGENT: [Agent Name]
TYPE: Decision / Direction / Approval
CONTEXT: One sentence — what you were working on when this arose.
THE ASK: The specific question or choice, stated plainly.
OPTIONS:
  A. [concrete option]
  B. [concrete option]
  C. [concrete option, if needed — maximum three]
RECOMMENDATION: Which option and one sentence why.
IF NO RESPONSE: Stop and wait.
BLOCKS AFFECTED: Which CLIVE blocks this touches.
```

Types: Decision (owner chooses between options), Direction (agent is stuck or
outside remit), Approval (clear recommendation, needs sign-off).

Never ask open-ended questions. Never bundle asks.
If you have more than one ask, submit the highest-priority one and wait.

---

## Decisions Log

All architectural decisions are in DECISIONS.md at the repo root.
Full ADR files are in docs/decisions/. Git history is the audit trail.
Notion is a read-only view — do not edit decisions in Notion.

Highest decision ID at time of writing: D-102.

If implementation reveals a gap or conflict not covered by existing
decisions, stop and flag it. Do not resolve design questions in code.

---

## Commit Conventions

```
feat: <description>     # New capability
fix: <description>      # Bug fix
chore: <description>    # Infrastructure, tooling, config
docs: <description>     # Documentation only
test: <description>     # Tests only
```

Commit one logical unit at a time. Do not bundle infrastructure and
application code in the same commit.

---

## Environment Variables

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

---

## Using /goal in This Repo

`/goal` is appropriate for bounded, verifiable work units. Examples:

```
/goal Block 8 requirements are complete: all open questions in the CLIVE spec
      for Block 8 are resolved into decisions, recorded in DECISIONS.md,
      and confirmed by the owner. No technology choices made.

/goal .claude/agents/ contains all seven agent files with valid frontmatter
      and system prompts fetched from Notion. Each file passes
      `cat .claude/agents/*.md` without error.
```

Set a turn cap. Recommend: `/goal [condition] — max 20 turns`.
One goal per session. Clear it before starting a new one.

The evaluator reads the transcript. Write goals as things the transcript
can demonstrate (Notion write confirmed, file committed, test passed).

---

## Skills

Skills live in `.claude/skills/` and are auto-discovered by Claude Code.
Claude reads every skill description and loads the skill when a task matches.
You do not invoke them manually unless you want to — they load automatically.

**fetch-decisions** — Reads DECISIONS.md from the repo root at session start.
Loads automatically when sessions begin or when decisions need verifying.
Ensures every agent follows the same read-confirm-flag-proceed sequence.
If DECISIONS.md is missing, this skill stops the session and waits.

**record-decision** — Enforces the decision protocol format for every ask
to the owner. Loads automatically when an agent raises a decision, direction,
or approval ask. Also handles DECISIONS.md flagging when a session produces
a significant decision that needs recording.

**event-schema** — Defines how blocks communicate through the Central
Orchestrator (D-003). Loads automatically when designing inter-block
interfaces. Provides the standard event definition format, naming conventions,
a cross-block dependency flag format, and full worked examples.

**requirements-output** — Defines what a complete block requirements document
looks like and what "done" means. Loads automatically during requirements
deepening sessions. Provides the standard nine-section structure, done
criteria, and a ready-to-fill template. Makes `/goal` completion conditions
for requirements work verifiable.

---

## Session Start Checklist

Every session, before acting on any instruction:

- [ ] Read DECISIONS.md from the repo root and confirm highest decision ID
- [ ] State which blocks or work are in focus for this session
- [ ] Flag any DECISIONS.md entries marked "Under Review" relevant to this session
- [ ] Confirm which agents are active and which are not yet activated
- [ ] Proceed

If DECISIONS.md is missing or unreadable, stop and report. Do not proceed.

---

## Pre-Launch Checklist

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

---

## What Claude Code Does Not Do in This Repo

- Does not make technology choices during requirements work
- Does not modify the alignment constitution
- Does not activate a specialist without owner approval
- Does not take irreversible actions without the confirmation gate
- Does not proceed past a decision point without an owner response
- Does not write to DECISIONS.md — flags what needs recording, Architect writes

---

*CLIVE workspace file — CLAUDE.md*
*Maintained alongside the project. Update only via recorded decision.*
