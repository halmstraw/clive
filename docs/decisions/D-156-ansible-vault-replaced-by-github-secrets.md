---
id: D-156
title: Ansible vault replaced by GitHub Secrets as source of truth for Ansible variables
status: Accepted
date: 2026-05-17
blocks: Block 27, Block 28, Block 29
agents: Infrastructure Agent
---

## Context

Migrating Block 25 observability from self-hosted Grafana to Grafana Cloud
(D-117 superseded) required adding five new Grafana Cloud credentials to the
Ansible vault. This exposed the vault as a maintenance burden: the same secrets
already existed in GitHub Actions, requiring them to be kept in sync across two
separate stores. The vault.yml file (gitignored, locally encrypted) was a
separately-managed artefact that duplicated GitHub Secrets and added operational
friction without adding security value.

## Decision

**Ansible vault (vault.yml) is removed. GitHub Secrets is the single source
of truth for all Ansible variables.**

The `.github/workflows/ansible.yml` workflow generates a temporary JSON vars
file from GitHub Secrets environment variables at run time, passes it to
`ansible-playbook` via `--extra-vars`, and deletes it immediately after the
run. The file is never committed and lives only in `/tmp/` for the duration
of the Ansible job.

`infrastructure/ansible/vault.example.yml` is repurposed as a reference guide
documenting every required variable and its corresponding GitHub Secret name.
It contains no real values.

## Consequences

- One secret store to maintain (GitHub Secrets) instead of two.
- Rotating a secret means updating GitHub Secrets once; the next Ansible run
  picks it up automatically.
- Initial VM provisioning (before the runner exists) requires a local run
  using the vars guide in `vault.example.yml` to construct a temporary file.
- The `ANSIBLE_VAULT_PASSWORD` GitHub Secret is no longer needed and should
  be deleted.
- CI Ansible lint no longer needs vault decryption — the lint step is simpler.

## Related decisions

- D-157 — Ansible playbook split into initial-setup and day-2 plays
- D-075 — GitHub Actions as CI/CD pipeline tool
- D-090 — self-hosted runner on VM
- D-091 — Terraform CI plan auto; apply manual only (same principle applied
  to Ansible)
