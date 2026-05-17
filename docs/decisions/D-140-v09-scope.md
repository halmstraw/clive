---
id: D-140
title: CLIVE v0.9 scope — Block 10 (Workers) primary; Block 12 (Context Window) closes partial
status: Accepted
date: 2026-05-17
blocks: Block 10, Block 12, Block 13, Block 9, Block 16, Block 23, Block 25
agents: Architect
---

## Context

v0.8 is signed off (D-139). The next sprint targets Block 10 (Workers /
Background Agents), which has had no delivery to date. Block 12 (Context
Window) has a partial decision record (D-044) but no standalone policy
document or named constants in code — it will be closed in this sprint
without adding new Telegram commands or surfaces.

## Options Considered

Not applicable — owner-directed scope definition.

## Decision

CLIVE v0.9 scope is:

**Primary block: Block 10 — Workers / Background Agents**

Two workers are delivered in this sprint:

1. **daily_digest** — proactive daily Telegram summary delivered at 08:00 UTC
   via cron. Queries last-24h operational data (query count, confirmed actions,
   LLM spend, feedback count, system health) and delivers formatted summary via
   the Telegram /alert endpoint.

2. **knowledge_maintenance** — weekly stale chunk flagging delivered at 09:00
   UTC every Monday via cron. Identifies chunks with zero retrievals older than
   a configurable threshold (default 90 days) and routes up to 5 per run to the
   owner via Block 9 confirmation gate (D-006 applies). No autonomous deletion.

No new Telegram commands. No new surfaces.

**Closing partial: Block 12 — Context Window**

Block 12 is closed by delivering:
- A policy document at `docs/spec/Block 12 - Context Window Policy.md`
  capturing all context window policy decisions (budget, priority ordering,
  token limits, allocation strategy)
- `context.py` in Block 8 declares all policy parameters as named constants
  and references the policy document in its module docstring

Block 12 does not add new runtime behaviour. It formalises existing behaviour
established under D-044.

## Constraints

- D-006 (confirmation gate) applies to all knowledge_maintenance deletions —
  no autonomous irreversible action.
- D-003 (event bus) applies — workers communicate through Block 13 only.
- Workers are registered in both tool_registry (Block 17) and the new workers
  table before first execution.
- Block 21 (Evolution Engine) remains paused per D-042.

## Consequences

- Block 10 gains its first production workers and its runtime infrastructure
  (scheduler, scoped capability dict, worker_runs log).
- Block 12 is formally closed with a policy document.
- Block 8 retrieval_count tracking (AC-7 in D-141) is a prerequisite for
  knowledge_maintenance to identify stale chunks.
- Future workers register in the same workers table and follow the same
  scope enforcement pattern.

## Related Decisions

- D-139 — v0.8 signed off (gate condition for this entry)
- D-040 — build-phase agents vs runtime workers distinction
- D-044 — Block 8 dynamic context allocation (Block 12 partial)
- D-006 — confirmation gate (applies to knowledge.prune action)
- D-003 — event bus principle (all worker→system communication via Block 13)
- D-141 — v0.9 acceptance criteria
