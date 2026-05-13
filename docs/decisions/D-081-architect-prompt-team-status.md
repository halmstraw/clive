---
id: D-081
title: Architect team status table removed from system prompt; lives in Notion task list
status: Accepted
date: 2026-05-01
blocks: Block 29 (Documentation)
agents: Architect
---

## Context
The team status table embedded in the Architect system prompt went stale
silently — specialists had been activated but the prompt still listed them
as inactive. Static content in a system prompt cannot be updated from
outside the prompt.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The Architect's team status table is removed from the Architect system
prompt. Authoritative team status lives in the Notion task list page
(CLIVE Build — Open Task List). The Architect fetches that page at session
start alongside DECISIONS.md. The system prompt contains only the fetch
instruction, not the table content.

## Rationale
The team table embedded in the system prompt went stale silently — specialists
had been activated and delivered artefacts, but the prompt still listed them
as inactive. This caused an evaluation paper to contain multiple incorrect
risk findings. Root cause: static content in a system prompt cannot be
updated from outside the prompt. Moving team status to Notion applies the
same pattern as D-033: state lives in a central store, not inside an agent's
context.

## Consequences
Rules out embedding team status inside any agent's system prompt. Rules out
the Architect acting on team status without fetching the live Notion page
first.

## Related Decisions
D-018 (agents are stateless), D-033 (state in central store).
