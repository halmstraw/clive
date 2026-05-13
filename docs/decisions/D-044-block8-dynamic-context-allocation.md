---
id: D-044
title: Block 8 context assembly uses dynamic allocation with priority ordering
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 12 (Context Window)
agents: Intelligence Agent
---

## Context
Fixed context allocation wastes budget early in conversations when history
is minimal. The context window must accommodate personality, alignment rules,
conversation history, and retrieved knowledge with no wasted space.

## Options Considered
A. Fixed ratio allocation across all tiers — wastes context; personality
   and history compete for the same budget.
B. Dynamic allocation with priority ordering and minimum guarantees (chosen)
   — efficient, handles short and deep conversations without waste.

## Decision
Block 8 context assembly uses dynamic allocation with priority ordering.
Tier 1 (personality) and Tier 2 (alignment rules) take what they need first.
Remaining budget splits between Tier 3 (conversation history) and Tier 4
(retrieved knowledge) with a minimum guarantee for each, surplus flowing
to whichever has more content.

## Rationale
Fixed allocation wastes context budget early in conversations when history
is minimal. Dynamic allocation with minimum guarantees handles both short
conversations (more budget to retrieval) and deep conversations (more budget
to history). Personality and alignment are small fixed costs.

## Consequences
Rules out fixed ratio allocation across all tiers at v0.1. Rules out any
scheme where personality or alignment documents compete for budget with
retrieval or history.

## Related Decisions
D-039 (personality as versioned document), D-047 (confidence signal),
D-043 (orchestrator-mediated retrieval).
