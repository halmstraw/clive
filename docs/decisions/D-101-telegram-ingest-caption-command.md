---
id: D-101
title: Telegram /ingest uses caption command pattern
status: Accepted
date: 2026-05-09
blocks: Block 23 (Telegram Surface), Block 14 (Ingestion)
agents: Experience Agent (not yet activated), Knowledge Agent
---

## Context
Block 23 (Telegram surface) must support a `/ingest` command that accepts a
file attachment. Telegram's bot API has two patterns: caption-based commands
(command sent as the message caption on a file upload) and two-step commands
(send command first, then upload file separately).

## Options Considered
A. Caption command pattern — send file with `/ingest` as the caption (chosen)
   — single interaction; file and command arrive together; simpler handler.
B. Two-step: send `/ingest`, then upload file — two interactions; requires
   stateful conversation tracking between messages.

## Decision
The Telegram `/ingest` command uses the caption command pattern. The owner
sends a file to the Telegram bot with `/ingest` as the message caption. The
file and command arrive in a single message; no multi-step interaction is
required.

## Rationale
Single interaction is simpler for the owner and simpler to implement.
The caption command pattern avoids the need for stateful conversation tracking
between separate messages, which would require Block 5 (Sync/State) involvement
at v0.2 before Block 5 is built.

## Consequences
Rules out two-step `/ingest` flow at v0.2. Caption must be present for the
command to be recognised; a file sent without caption is not treated as an
ingest request.

## Related Decisions
D-099 (v0.2 scope), D-014 (Block 14 ingestion), D-039 (Telegram surface).
