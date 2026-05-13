---
id: D-023
title: Central Orchestrator runs as single instance with no redundancy in v1
status: Accepted
date: 2026-05-01
blocks: Block 13 (Central Orchestrator), Block 27 (Infrastructure/IaC),
        Block 25 (Observability)
agents: Systems Agent, Infrastructure Agent
---

## Context
Redundancy adds significant complexity — leader election, shared state
synchronisation, split-brain handling. For a single-owner personal system,
this complexity may not be warranted.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Central Orchestrator (Block 13) runs as a single instance with no
redundancy in v1.

## Rationale
Simplicity and debuggability outweigh availability for a single-owner
personal system.

## Consequences
Rules out leader/follower redundancy in v1. Rules out a distributed
orchestrator in v1. Orchestrator downtime means bus downtime — this
is accepted under D-027's recovery time tolerance.

## Related Decisions
D-062 (in-process event bus), D-063 (long-running container),
D-064 (single cloud VM), D-027 (point-in-time recovery).
