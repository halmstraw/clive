---
id: D-157
title: Ansible playbook split into initial-setup and day-2 tagged plays
status: Accepted
date: 2026-05-17
blocks: Block 27, Block 28
agents: Infrastructure Agent
---

## Context

The GitHub Actions self-hosted runner (D-090) runs as the `clive` service user,
which has no sudo access (by design — granting a CI runner user full root sudo
is an unacceptable security risk on a personal system). The original Ansible
playbook used `become: true` at the play level, making it impossible to run
from the self-hosted runner for any task.

Analysis showed a clear split: system-level roles (base, docker, backup-cron,
github-runner) require root and run once at initial VM provisioning; application
roles (clive-secrets, compose-deploy, postgres-init) write only to paths owned
by clive and never need root.

## Decision

**The Ansible playbook is split into two tagged plays:**

**`initial-setup`** (tag: `initial-setup`) — `become: true`, run manually as
root from a local machine during first-time VM provisioning:
- `base` — OS packages, ufw, fail2ban, service user
- `docker` — Docker Engine installation
- `backup-cron` — rclone config, nightly backup cron
- `github-runner` — runner registration and systemd service

**`day-2`** (tag: `day2`) — `become: false`, run via
`.github/workflows/ansible.yml` on the self-hosted runner as `clive`:
- `clive-secrets` — writes `/etc/clive/secrets.env`
- `compose-deploy` — copies compose, SQL, and observability config files;
  restarts Alloy to apply updated credentials
- `postgres-init` — applies SQL migrations and sets role passwords

The `clive` user is **not** granted passwordless sudo. The day-2 play is
designed so root is never needed: all destination paths are owned by `clive`,
`owner:`/`group:` attributes are omitted from copy tasks (files created by
`clive` are owned by `clive` automatically), and `become_user: clive` is
removed from tasks that were already running as `clive`.

## Consequences

- Routine secret rotation and config updates run fully automated via GitHub
  Actions with no manual SSH step.
- The CI runner is never granted root — attack surface is contained.
- Initial VM provisioning remains a manual step (rare; typically once per VM
  rebuild). Instructions are in `docs/runbooks/terraform-bootstrap.md`.
- `ansible-playbook` on the VM requires `ansible` to be pre-installed by the
  `base` role; the workflow does not install it at runtime.

## Related decisions

- D-156 — Ansible vault replaced by GitHub Secrets
- D-090 — self-hosted runner on VM; no inbound SSH from CI
- D-091 — Terraform CI plan auto; apply manual only
- D-083 — CLIVE infrastructure under cliveai@proton.me
