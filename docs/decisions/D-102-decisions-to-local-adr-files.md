---
id: D-102
title: Decisions migrated from Notion to local ADR files
status: Accepted
date: 2026-05-13
blocks: Block 29 (Documentation)
agents: All agents — changes session-start fetch procedure
---

## Context
D-033 established Notion as the single source of truth for DECISIONS.md and
replaced the project file with a pointer. Over time, the fetch-at-session-start
pattern created friction: Notion authentication is required on every session,
WebFetch cannot reach authenticated pages, and the Notion MCP is needed as a
workaround. The decision log has grown to 101 entries and will continue to grow.
Git history provides a more durable audit trail than Notion page history.

## Options Considered
A. Keep Notion as source of truth, improve the MCP-based fetch — retains a
   network dependency and external service as a hard blocker for session start.
B. Migrate to local ADR files in the repo; Notion becomes a read-only view —
   session start requires only a local file read; git is the audit trail.
C. Dual-write to both — adds maintenance overhead and creates two sources
   that will inevitably diverge.

## Decision
The decision log is migrated to the repository as individual ADR files
(docs/decisions/D-NNN-*.md), with DECISIONS.md at the repo root serving as
the master index. Notion is retained as a read-only reference view only.
The fetch-decisions skill is updated to read the local file.

## Rationale
Local files remove the network and authentication dependency from session
start. Git history provides an auditable, immutable record of every decision
change — stronger than Notion page history. Individual ADR files make each
decision independently linkable, reviewable, and diffable.

## Consequences
Session start no longer requires Notion connectivity. All decision changes
are visible in git log and PR diffs. The Notion page becomes a convenience
view, not the source of truth. Any agent that fetches decisions must read
DECISIONS.md from the repo root, not from Notion.

## Related Decisions
Supersedes D-033 (Notion as source of truth for DECISIONS.md).
Consistent with D-008 (decisions recorded before implementation begins).
Consistent with D-018 (state in central store — the repo is the store for
build artefacts).
