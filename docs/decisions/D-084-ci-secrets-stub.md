---
id: D-084
title: CI pipeline creates stub secrets file from .env.example; never committed
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD), Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent
---

## Context
The CI pipeline needs to run `docker compose config` to validate the Compose
file structure. The Compose file references secrets via env_file, which must
exist for the config check to pass.

## Options Considered
A. Stub from .env.example in CI step (chosen) — lowest complexity; no
   committed override file; empty values sufficient for structural lint.
B. Separate docker-compose.ci.yml override — additional file to maintain;
   divergence risk from production config.
C. Remove docker compose config from CI — removes validation entirely.

## Decision
The CI pipeline creates a stub secrets file from `.env.example` (empty
values) before running `docker compose config`. The stub is created as a
temporary step in the GitHub Actions workflow and is never committed.
Production continues to use `/etc/clive/secrets.env` injected by Ansible.
No changes to the production Compose file.

## Rationale
The `.env.example` file is already anticipated in CLAUDE.md as the local
development pattern. Using it as a CI stub is the lowest-complexity fix —
no separate Compose override file, no change to production config. Empty
values are sufficient for a structural config lint.

## Consequences
Rules out a separate docker-compose.ci.yml override file. Rules out removing
the docker compose config check from CI. Rules out any committed file
containing real secret values.

## Related Decisions
D-075 (GitHub Actions), D-072 (Compose + Ansible).
