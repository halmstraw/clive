---
id: D-057
title: Block 23 authentication at v0.1 is channel-as-authentication; no additional credential layer
status: Accepted
date: 2026-05-01
blocks: Block 23 (Security), Block 6 (Users, future), Block 7 (Trust Zones)
agents: Access & Security Agent (Block 23, future), Experience Agent
---

## Context
Single-owner (D-001) and single-surface (D-035) define a threat model focused
on device/account compromise, not network-level impersonation. An additional
credential layer adds complexity before there is evidence of need.

## Options Considered
A. Channel-as-authentication (chosen) — consistent with single-owner threat
   model; no extra credential management at v0.1.
B. Shared secret or per-session credential — adds complexity without
   proportionate security benefit given D-001 and D-035.
C. Multi-factor authentication — appropriate for multi-user; premature here.

## Decision
Block 23 authentication model at v0.1 is channel-as-authentication. The
surface channel itself is the authentication factor. No additional credential
layer at v0.1.

Condition: If CLIVE handles material sensitive to channel compromise before
v0.2, the authentication model is revisited before that version ships.

## Rationale
Single-owner (D-001) and single-surface (D-035) mean the threat model is
device/account compromise, not network-level impersonation. Channel trust
is consistent with how personal messaging apps work and avoids credential
management complexity before there is evidence of need.

## Consequences
Rules out shared secret or per-session credential requirement at v0.1.
Rules out multi-factor authentication at v0.1.

## Related Decisions
D-001 (single-owner), D-035 (v0.1 single-surface),
D-058 (Block 4 owns authentication boundary).
