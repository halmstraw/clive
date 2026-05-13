---
id: D-021
title: Implementation does not begin until Block 13 and Block 27 requirements are approved
status: Accepted
date: 2026-05-01
blocks: Block 13 (Central Orchestrator), Block 27 (Infrastructure/IaC)
agents: Systems Agent, Infrastructure Agent
---

## Context
Starting implementation before requirements are sufficiently understood
means building the wrong thing and discovering it late. The two highest-risk
blocks are the orchestrator and infrastructure — both have significant
hidden complexity.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Implementation does not begin until the Systems Agent and Infrastructure
Agent have produced sufficiently deepened requirements for Block 13 and
Block 27.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out parallel scaffolding during the requirements phase. Rules out
any code being written before Block 13 and Block 27 requirements are
approved by the owner.

## Related Decisions
D-002 (no technology choices at spec), D-017 (Block 13 and 16 first).
