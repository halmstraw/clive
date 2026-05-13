---
id: D-036
title: Business Layer (Blocks 30–38) out of v1 scope; gated behind named preconditions
status: Accepted
date: 2026-05-01
blocks: Blocks 30–38 (Business Layer)
agents: Business Agent (future, not activated in v1)
---

## Context
The Business Layer enables autonomous income identification, marketing,
contracting, and payment. This is qualitatively different from a personal
assistant and raises legal, financial, and continuity questions that
technical decisions cannot resolve.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Business Layer (Blocks 30–38) is out of v1 scope. The Business Agent
is not activated during v1. Re-entry to scope is gated behind all five
preconditions being satisfied: legal entity chosen and registered; tax
treatment confirmed with a qualified accountant; owner-incapacitation
contingency documented; pre-approved income category list defined;
client-data jurisdiction decided.

## Rationale
Technical decisions D-022 through D-034 cover the substrate but cannot
resolve real-world legal and fiduciary questions. Naming the gates
preserves the future option without forcing premature commitment or design
effort during v1.

## Consequences
Rules out activating the Business Agent during v1. Rules out designing or
deepening Blocks 30–38 during v1. Rules out any income-generating activity
by CLIVE in v1. Lifting the scope-out requires all preconditions met and
a discrete superseding decision.

## Related Decisions
D-007 (no fixed business model at initialisation),
D-035 (v0.1 scope definition).
