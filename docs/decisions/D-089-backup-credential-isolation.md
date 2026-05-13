---
id: D-089
title: Dedicated Hetzner Object Storage access key for backup; isolated from app credentials
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 16 (Storage)
agents: Infrastructure Agent, Knowledge Agent
---

## Context
The backup-cron role needs object storage credentials to copy backups to
Hetzner Object Storage. Reusing the application credential (`clive-app`)
would mean a single credential compromise exposes both the application and
backup access.

## Options Considered
A. Dedicated backup key (clive-backup), isolated from app and Terraform
   credentials (chosen) — credential compromise is bounded per key.
B. Reuse clive-app credentials — single compromise exposes both app and
   backup access paths.

## Decision
A dedicated Hetzner Object Storage access key (`clive-backup`) is created
for the backup-cron role. Backup credentials are isolated from the application
credentials (`clive-app`) and the Terraform state credentials (`clive-terraform`).

## Rationale
Credential isolation is cheap and correct. Compromise of one key does not
expose the others. The backup process has a distinct access pattern from the
application and should have its own credential boundary.

## Consequences
Rules out reusing `clive-app` credentials for backups. Rules out any shared
credential across backup and application access paths.

## Related Decisions
D-068 (S3 raw store), D-069 (object store backup requirement).
