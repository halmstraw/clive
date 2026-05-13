---
id: D-066
title: Block 16 relational/state store shares the PostgreSQL instance with search index
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 13 (Orchestrator), Block 27 (Infrastructure/IaC)
agents: Knowledge Agent, Infrastructure Agent
---

## Context
D-065 chose PostgreSQL with pgvector for the search index. The relational/state
store could share that instance or be a separate service.

## Options Considered
A. Same PostgreSQL instance, separate schemas (chosen) — one service to
   operate and back up; consistent with D-023.
B. Separate PostgreSQL instance — failure isolation benefit real but
   inconsistent with D-023 simplicity preference.
C. SQLite or embedded database — migration burden the moment write
   concurrency increases.

## Decision
Block 16's relational/state store uses the same PostgreSQL instance as the
search index (D-065), with separate schemas for search and state concerns.

## Rationale
One database service to operate, back up (D-056), and reason about. The
failure isolation benefit of a separate instance is real but inconsistent
with D-023's explicit simplicity preference. SQLite would create a migration
burden the moment write concurrency increases.

## Consequences
Rules out a separate PostgreSQL instance for the state store at v0.1. Rules
out SQLite or embedded database for the state store. Rules out any state
store technology other than PostgreSQL at v0.1.

## Related Decisions
D-065 (PostgreSQL + pgvector for search),
D-067 (append-only audit log), D-056 (24-hour backup window).
