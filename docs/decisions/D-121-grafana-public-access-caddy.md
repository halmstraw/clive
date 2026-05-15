---
id: D-121
title: Grafana exposed publicly via Caddy reverse proxy at grafana.halmshaw.co.uk
status: Accepted
date: 2026-05-15
blocks: Block 25, Block 27
agents: Infrastructure Agent
---

## Context
Grafana was bound to `127.0.0.1:3000` on the VM — accessible only via SSH
tunnel. Owner approved public access via Caddy reverse proxy with TLS and
Google OAuth authentication.

## Decision
Caddy is added as a Docker Compose service. It terminates TLS for
`grafana.halmshaw.co.uk` via Let's Encrypt and reverse-proxies to the
internal `grafana:3000` service. Grafana's direct port binding is removed.

Hetzner firewall rules are updated to allow inbound TCP on ports 80 and 443
from any source (required for Let's Encrypt HTTP challenge and HTTPS access).

Authentication is handled by Grafana's built-in Google OAuth
(`GF_AUTH_GOOGLE_*` env vars). Owner must create a Google Cloud OAuth
application and supply `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in
`/etc/clive/secrets.env`. Until Google OAuth is configured, the existing
admin username/password login remains active.

DNS prerequisite: A record for `grafana.halmshaw.co.uk` → `138.199.149.201`
must be in place before Caddy can obtain a TLS certificate.

## Consequences
Grafana is reachable at `https://grafana.halmshaw.co.uk` without an SSH
tunnel. Ports 80 and 443 are open to the public internet on the VM — a
change from the previous posture (inbound HTTP/HTTPS blocked). Google OAuth
restricts login to the owner's Google account once credentials are supplied.
