---
id: D-037
title: Block 22 alignment gate is deterministic rules-and-schema; no LLM-as-judge in v1
status: Accepted
date: 2026-05-01
blocks: Block 22 (Alignment Layer), Block 13 (Orchestrator),
        Block 21 (Evolution Engine)
agents: Architect (Block 22), Systems Agent (Block 13, Block 21)
---

## Context
The alignment gate is the system's most safety-critical chokepoint.
The mechanism class must be decided before Block 22 has technical meaning.
LLM-as-judge introduces an unbounded failure mode at exactly the wrong place.

## Options Considered
A. Deterministic rules-and-schema (chosen) — auditable, consistent,
   no hallucinated approvals.
B. LLM-as-judge — flexible but introduces unbounded failure mode at
   the most critical chokepoint.
C. Hybrid rules-plus-LLM — adds complexity without clear benefit in v1.

## Decision
The Block 22 alignment gate is implemented as a rules-and-schema mechanism.
Bridge-origin events declare effect type from a constrained vocabulary;
deterministic rules check the declaration against permitted operations.
Closed-failure if no rule positively confirms permission. LLM-as-judge
deferred to v2.

## Rationale
The alignment gate is the system's most safety-critical chokepoint.
LLM-as-judge at this location introduces an unbounded failure mode —
hallucinated approvals — at exactly the wrong place. Deterministic rules
are debuggable, auditable, and consistent with D-023's simplicity
preference.

## Consequences
Rules out LLM-as-judge as the primary alignment mechanism in v1. Rules out
hybrid rules-plus-LLM gates in v1. Rules out any alignment gate that cannot
positively confirm permitted operation against a declared rule.

## Related Decisions
D-004 (alignment boundary), D-030 (experimental events trust class),
D-060 (Architect authors the ruleset).
