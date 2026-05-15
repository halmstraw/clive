---
id: D-119
title: Telegram /help command — lists all available commands and usage
status: Accepted
date: 2026-05-15
blocks: Block 23, Block 3
agents: Architect
---

## Context
As the number of Telegram commands grows (query, /ingest, /ingest_confirm,
/delete, /list, /status, /feedback), the owner has no single place to discover
what is available and how to invoke each one. There is no discoverability
mechanism in the current surface.

## Decision
A `/help` command is added to the Telegram surface (Block 23). When invoked,
CLIVE returns a formatted message listing every available command, its syntax,
and a one-line description of what it does.

The help text must remain current: whenever a new command is added or an
existing command's syntax changes, the /help response is updated in the same
change set. Stale help text is treated as a defect.

At time of recording, the command inventory to be covered is:

| Input | Description |
|---|---|
| (plain text) | Ask CLIVE a question |
| /ingest | Ingest a document — send file with `/ingest` as caption (desktop), or send file then reply `/ingest_confirm` (mobile) |
| /ingest_confirm | Confirm a pending mobile ingest |
| /delete `<filename>` | Delete an ingested document (requires confirmation) |
| /list | List all ingested documents |
| /status | Show system health and component status |
| /feedback | Mark the most recent response as poor quality |
| /help | Show this help message |

## Consequences
Block 23 (Telegram Surface) gains one new command handler. The Experience Agent
owns the implementation. Help content is the responsibility of whichever agent
delivers the associated command; the Experience Agent reviews all help text for
consistency of tone and format before each release.
