---
id: D-010
title: All agents use the standard decision protocol when approaching the owner
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — defines the communication protocol with the owner
---

## Context
Multiple agents raising questions in different formats creates confusion and
makes it hard for the owner to track decisions, give consistent responses,
and maintain alignment across the build.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
All agents use a standard decision protocol when approaching the owner.
No variations.

Protocol fields: AGENT / TYPE / CONTEXT / THE ASK / OPTIONS (max 3) /
RECOMMENDATION / IF NO RESPONSE / BLOCKS AFFECTED

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out open-ended questions to the owner. Rules out bundled asks. Rules
out agents proceeding without a response. Every owner interaction follows
the same predictable format.

## Related Decisions
D-011 (one ask per message, submitted in priority order).
