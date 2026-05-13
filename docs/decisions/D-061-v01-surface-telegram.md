---
id: D-061
title: v0.1 surface is Telegram
status: Accepted
date: 2026-05-01
blocks: Block 23 (Security), Block 4 (Interface/Egress),
        Block 2 (Multi-Surface), Block 13 (Orchestrator)
agents: Experience Agent (Block 23, Block 4, Block 2),
        Systems Agent (Block 13)
---

## Context
D-035 deferred the surface choice to a separate decision. The surface must
satisfy Block 23's interface contract requirements with minimal custom build
work for v0.1.

## Options Considered
A. Telegram (chosen) — text in/out, channel-as-authentication (D-057),
   reliable delivery, cross-device, minimal build work.
B. CLI — requires physical access to the VM; not ambient.
C. Custom web UI or native app — significant build work before the substrate
   is validated; out of scope per D-035.

## Decision
The v0.1 surface is Telegram. CLIVE communicates with the owner via a
Telegram bot at v0.1.

## Rationale
Telegram satisfies every Block 23 interface contract requirement — text in,
text out, channel-as-authentication (D-057), reliable event delivery,
cross-device by default. It requires the least custom surface build work
and is the fastest path to a working v0.1. No third-party surface dependency
introduces less risk than a custom app at this stage.

## Consequences
Rules out CLI, web UI, native app, or any other surface at v0.1. Rules out
multi-surface operation at v0.1 (already ruled out by D-035).

## Related Decisions
D-035 (v0.1 single-surface scope), D-057 (channel-as-authentication),
D-094 (v0.1 signed off).
