---
id: D-108
title: Framework adoption — narrower subset approved; Redis and OpenJarvis gated on formal review
status: Accepted
date: 2026-05-14
blocks: Block 10, Block 13, Block 15, Block 16, Block 17, Block 22
agents: All agents
---

## Context
The owner proposed accelerating CLIVE's implementation via a hybrid adoption
strategy: OpenJarvis (Blocks 1–5, 8–18), Redis 8 as event bus transport and
vector store, MCP as Block 17 tool contract, and PocketFlow patterns for worker
flows. The Architect assessed the proposal against standing decisions and
surfaced two hard constraint violations and four known unknowns before any
adoption decision was taken.

## Options Considered

A. Adopt the full hybrid as proposed — requires formally superseding D-062 and
   D-065, resolving four known unknowns (D-003, D-004, D-005, D-006 compliance
   of OpenJarvis), and 6–10 weeks of rebuild across specialists. v0.3 deferred
   until substrate settled.

B. Adopt a narrower subset only: MCP as Block 17 tool contract; PocketFlow
   patterns for Block 10/15 worker flow declarations. Reject Redis event bus
   (D-062 conflict) and Redis vector store (D-065 conflict). Gate OpenJarvis
   adoption on formal architecture verification against D-003, D-004, D-005,
   D-006 before assigning any blocks to it. v0.3 proceeds uninterrupted.

C. Reject all framework adoption — continue from-scratch build, accept longer
   timeline.

## Decision

Option B selected. Owner approved 2026-05-14.

**Adopted immediately:**
- MCP (Model Context Protocol) as the tool contract format for Block 17 (Tool
  Registry). No library dependency — MCP is a schema standard. No conflicts
  with standing decisions.
- PocketFlow *patterns* (not the library) for declaring worker flows as explicit
  directed graphs in Blocks 10 and 15. Supports D-003 (event bus principle)
  by making flow structure explicit. No library lock-in.

**Rejected:**
- Redis 8 as event bus transport for Block 13. Hard conflict with D-062
  (in-process pub/sub, no external broker). D-062 stands.
- Redis 8 as vector storage for Block 16. Hard conflict with D-065 (PostgreSQL
  + pgvector). D-065 stands.

**Gated on formal review:**
- OpenJarvis adoption for any CLIVE block. Cannot proceed until the following
  are formally resolved:
  1. D-003 compliance: does OpenJarvis's internal agent runtime route all
     inter-block calls through Block 13, or does it bypass the event bus?
     If it cannot be re-routed through Block 13 without fighting the framework,
     adoption is disqualified.
  2. D-004 compliance: is OpenJarvis's learning loop bounded to means
     optimisation only, or can it modify goals (ends)? Scope must be formally
     documented and bounded against the alignment constitution before adoption.
  3. D-005 compliance: does OpenJarvis's skill/learning loop reach personality
     parameters, or can Block 1 (personality document, D-048) be reliably
     shielded from it?
  4. D-006 compliance: does OpenJarvis's tool execution model honour the Block 9
     confirmation gate, or does it execute tools on LLM instruction without
     explicit human confirmation?

**Unaffected:**
- v0.3 scope (D-105) and acceptance criteria (D-106): T8 (deletion via Block 9
  Action Layer) and Block 18 (Feedback) proceed immediately on the existing
  substrate. No substrate change.

## Rationale

MCP and PocketFlow patterns accelerate Block 17 and worker flow design with no
standing conflicts and minimal lock-in. The Redis and OpenJarvis components
failed constraint checks: Redis violates two accepted decisions outright;
OpenJarvis has four known unknowns that could each independently disqualify it.
Bundling safe components with unverified ones in a single yes/no was the wrong
framing — Option B separates them correctly. The known unknowns must be resolved
through formal architecture review before OpenJarvis is reconsidered.

## Consequences

- D-062 (in-process event bus) and D-065 (PostgreSQL + pgvector) remain in
  force. No superseding decisions are needed for v0.3.
- Block 17 design work may proceed with MCP as the tool contract schema.
- Block 10 and Block 15 worker flow design may use PocketFlow directed-graph
  patterns as a declaration style.
- OpenJarvis adoption is blocked until all four gate conditions above are
  resolved in writing and presented to the owner as a new decision.
- v0.3 (T8 + Block 18) is not delayed. It continues on the existing substrate
  with no changes to Block 13, Block 16, or Block 8.
- The Evolution Engine (Block 21) remains paused per D-042.

## Related Decisions

D-003 (event bus principle), D-004 (alignment boundary), D-005 (personality
survives Reaper), D-006 (confirmation gate), D-062 (in-process event bus),
D-065 (PostgreSQL + pgvector), D-077 (LiteLLM abstraction), D-105 (v0.3 scope),
D-106 (v0.3 acceptance criteria).
