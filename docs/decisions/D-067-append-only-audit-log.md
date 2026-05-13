---
id: D-067
title: Block 16 audit log is append-only table with INSERT-only database role
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 13 (Orchestrator), Block 27 (Infrastructure/IaC),
        Block 22 (Alignment Layer)
agents: Knowledge Agent, Infrastructure Agent, Architect (Block 22)
---

## Context
D-027 requires immutability of the audit log to be enforceable at the
storage layer. Application-layer policy alone is not a sufficient guarantee.

## Options Considered
A. INSERT-only database role (chosen) — structural guarantee at the
   permission boundary; does not rely on application discipline.
B. Application-layer immutability only — relies on every code path
   respecting the constraint; weaker guarantee.
C. Separate append-only log service or write-once object store — additional
   service; inconsistent with D-023 and D-064.

## Decision
Block 16's audit log is an append-only table in the same PostgreSQL instance,
accessed via a dedicated INSERT-only database role. The application's audit
writer connects as this restricted role. No UPDATE or DELETE privileges are
granted to this role under any circumstance.

## Rationale
D-027 requires immutability to be enforceable at the storage layer. An
INSERT-only database role enforces immutability at the permission boundary —
a structural guarantee that does not rely on application discipline alone.

## Consequences
Rules out application-layer-only immutability enforcement for the audit log.
Rules out a separate append-only log service or write-once object store at
v0.1. Rules out any database role with UPDATE or DELETE privileges on the
audit table. Note: ON CONFLICT DO NOTHING on the audit log INSERT requires
SELECT privilege — the role must be granted INSERT, SELECT (D-094).

## Related Decisions
D-027 (point-in-time recovery), D-066 (single PostgreSQL instance),
D-093 (database role passwords via Ansible).
