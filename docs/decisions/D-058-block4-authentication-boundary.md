---
id: D-058
title: Block 4 owns inbound authentication boundary and attaches surface auth metadata
status: Accepted
date: 2026-05-01
blocks: Block 4 (Interface/Egress), Block 23 (Security),
        Block 9 (Action Layer), Block 13 (Orchestrator)
agents: Experience Agent (Block 4), Access & Security Agent (Block 23, future),
        Intelligence Agent (Block 9), Systems Agent (Block 13)
---

## Context
D-057 establishes channel-as-authentication. Someone must attach the
authentication metadata to inbound events. Block 4 is structurally the
only block that knows which channel an event arrived on.

## Options Considered
A. Block 4 attaches auth metadata; Block 23 defines rules (chosen) — clean
   separation; D-003 satisfied.
B. Block 23 directly inspects channel events — creates a Block 23 ↔ channel
   dependency, violating D-003.
C. Block 9 performs its own channel authentication — duplicates logic,
   creates an unprotected path if any event reaches Block 9 via other means.

## Decision
Block 4 (Interface/Egress) owns the authentication boundary on the inbound
channel. Block 4 attaches surface authentication metadata to inbound events
before they reach Block 13. Block 23 (Security) defines the authentication
rules and what constitutes a valid authenticated surface. Block 9 (Action
Layer) consumes the pre-authenticated event — it does not perform its own
channel authentication check.

## Rationale
Block 4 is the only block that knows which channel an inbound event arrived
on — it is structurally positioned to attach that metadata. Block 23 defines
the rules but does not need to understand channel mechanics to apply them.
This keeps authentication logic in Block 23 without creating a direct Block 23
↔ channel dependency, and satisfies D-003.

## Consequences
Rules out Block 23 directly inspecting channel events. Rules out Block 9
performing channel authentication independently. Rules out any inbound event
reaching Block 9 without surface authentication metadata attached by Block 4.

## Related Decisions
D-003 (event bus principle), D-057 (channel-as-authentication).
