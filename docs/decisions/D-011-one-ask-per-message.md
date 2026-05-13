---
id: D-011
title: One ask per message; multiple questions submitted separately in priority order
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: All agents — defines the communication cadence with the owner
---

## Context
Agents that bundle multiple questions in one message force the owner to
track several threads simultaneously and risk partial answers being acted
on as complete ones.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
One ask per message. Multiple questions are submitted separately in
priority order.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out multi-question messages. Rules out conditional asks ("if A then
also B"). Each agent message to the owner contains exactly one ask.

## Related Decisions
D-010 (standard decision protocol format).
