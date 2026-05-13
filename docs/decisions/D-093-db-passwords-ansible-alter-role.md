---
id: D-093
title: Database role passwords injected via Ansible ALTER ROLE; SQL files clean
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 16 (Storage)
agents: Infrastructure Agent, Knowledge Agent
---

## Context
PostgreSQL role passwords must be set during provisioning. Hardcoding passwords
in SQL init files would require committing secrets or templating SQL, both
problematic. Ansible already manages secrets and runs against the VM.

## Options Considered
A. Ansible ALTER ROLE tasks inject passwords at provision time; SQL files
   contain no secrets (chosen) — SQL files stay clean and committable; Ansible
   handles secret injection from `/etc/clive/secrets.env`.
B. Templated SQL files with Ansible vars — SQL files contain secret placeholders;
   harder to audit; mixing IaC and SQL concerns.
C. Passwords in SQL init files — requires committing secrets or a separate
   secret-substitution step; violates the no-secrets-in-code constraint.

## Decision
Database role passwords are injected via Ansible `ALTER ROLE` tasks at
provision time. SQL init files contain no passwords and remain clean and
committable. Ansible reads passwords from `/etc/clive/secrets.env` and applies
them via `ALTER ROLE ... PASSWORD`.

## Rationale
Keeps SQL files free of secrets and separately auditable. Ansible already owns
the secrets injection lifecycle. No new mechanism needed. Consistent with the
constraint that secrets never appear in committed files.

## Consequences
Rules out passwords in SQL init files. Rules out templated SQL files with
embedded secret placeholders.

## Related Decisions
D-064 (PostgreSQL roles), D-067 (audit log), D-072 (Ansible stack).
