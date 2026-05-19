---
id: D-160
title: Reject MemPalace as memory subsystem dependency for Block 11 / Block 16; carry forward three design patterns
status: Accepted
date: 2026-05-19
blocks: Block 11, Block 16, Block 7, Block 12, Block 13, Block 23
agents: Knowledge Agent
---

## Context

MemPalace is an open-source local-first AI memory system (ChromaDB + SQLite,
MIT licensed, released April 2026). It stores conversation history verbatim
and retrieves via semantic search organised by a spatial metadata schema
(wings / rooms / halls / drawers). At the time of evaluation it had high
public visibility with approximately 22,000 GitHub stars.

MemPalace was evaluated as a possible foundation for Block 11 (Memory
Management) and/or Block 16 (Storage). The evaluation drew on independent
code and benchmark reviews published by Vectorize and lhl/agentic-memory.

The evaluation was completed and the decision to reject was made by the owner.

## Reasons for Rejection

All six reasons are recorded as the constraint set that any future "should
we use X off-the-shelf memory system?" decision must be tested against.

**1. Architectural mismatch with D-003 (event bus principle).**
MemPalace is a CLI tool plus a single-client MCP server. It is not designed
to participate in an event-bus architecture where multiple blocks emit and
subscribe to events through a central orchestrator. Adopting it would require
wrapping it in a bus adapter, at which point the integration cost has been
paid without inheriting any native architectural benefit. D-003 requires that
all inter-block communication routes through Block 13; MemPalace's architecture
is fundamentally incompatible with that constraint.

**2. No write gating — conflict with D-006 and the alignment posture.**
Independent review (Vectorize) found no input sanitisation and no write gating:
any input is stored verbatim without content validation, creating a prompt
injection surface. CLIVE's memory store must be gated by Block 23 (Security)
and respect Block 7 (Trust Zones). "Store everything verbatim, no validation"
is the opposite shape from what D-006 requires. Writes to the memory store are
not irreversible actions in the same sense as deletion, but unvalidated ingestion
of attacker-controlled content into a store that feeds all future context
assembly is a first-class alignment risk. D-006 and the alignment posture
together require that writes be gated, not open.

**3. No contradiction detection, no entity resolution.**
Independent code analysis (lhl/agentic-memory) confirms the knowledge graph
lacks entity resolution and contradiction detection. Block 11 requires
episodic/semantic distinction and consolidation logic. Block 18 (Feedback /
Correction) requires the ability to detect when a stored fact was superseded
by a correction. MemPalace cannot identify that two stored facts contradict
each other, and it has no mechanism for preferring the more recent or
better-sourced version of a conflicting assertion.

**4. Benchmark claims are misleading.**
The public 100% LongMemEval score used targeted regex fixes for three failing
questions plus LLM reranking; the honest held-out figure is 98.4%. The 96.6%
raw figure is real but measures ChromaDB's default embedding model performance,
not MemPalace's spatial architecture — the spatial palace structure is not
involved in the headline benchmark. Maintainers have publicly acknowledged
this. CLIVE's design decisions must not be grounded in benchmarks that the
producing party has publicly qualified.

**5. Supply-chain risk.**
There is an active impostor domain (mempalace.tech) flagged by the maintainers
as potentially distributing malware. The authoritative source moved
organisations during the project's first weeks of existence. This is the class
of supply-chain risk that disqualifies a dependency from production by default.
No exception process applies; the risk profile is structurally unacceptable for
a single-owner personal AI system where the owner has no independent detection
layer for supply-chain compromise.

**6. Production maturity is low.**
Open issues against the official repository include MCP server failures on
Windows with non-ASCII content, and palace data loss on version upgrade.
Multiple users report sessions becoming slower as the memory store grows.
MemPalace has no "forget" mechanism and defers the problem to retrieval ranking,
which still consumes tokens and attention per surfaced result. These are not
edge-case bugs — they affect core functionality under ordinary usage conditions.

## Carried-Forward Design Inputs

Three patterns from MemPalace's design are worth absorbing into CLIVE's own
Block 11 / Block 16 / Block 12 designs. These are design inputs to be absorbed
as separate work; they are not implemented by this decision.

**A. Verbatim raw storage as the foundation, with derived/processed stores layered on top.**
The hypothesis that LLM-extracted summaries discard context that matters later
is correct. Block 16 already distinguishes raw store from processed store. This
decision reaffirms that the raw store is canonical and the processed store is
derived. No future Block 16 or Block 11 design should treat the processed or
summarised representation as the authoritative source of record; the original
verbatim content must be preserved and accessible.

**B. Tiered context-loading pattern for Block 12.**
Wake-up cost should be cheap (identity-layer + top-ranked memories), with
deeper retrieval triggered on demand. The tiering pattern is: identity →
top-ranked memories → topic-scoped context → deep semantic search, escalating
only when needed. This maps onto Block 12's responsibility to manage context
window composition without exhausting the token budget on every query. Concrete
token budgets are to be set during Block 12 design work; this decision records
the structural pattern only.

**C. Metadata-scoped retrieval as a pre-filter before semantic search.**
Filtering by zone / domain metadata before running vector similarity is an
efficiency and accuracy win, and maps directly onto Block 7 (Trust Zones).
Block 16's retrieval interface should support zone-scoped queries as a
primitive, not as a post-filter applied after vector search has already run
across the full corpus. This is consistent with D-050 (single zone "personal"
at v0.1) and positions the storage layer to support additional zones correctly
when they are introduced.

## Decision

MemPalace is rejected as a dependency for Block 11 (Memory Management) and
Block 16 (Storage). No CLIVE service will take a dependency on MemPalace or
any of its constituent components (ChromaDB instance, SQLite schema, or
palace spatial metadata structure) as packaged by the MemPalace project.

The six reasons above define the constraint set for evaluating any future
off-the-shelf memory system against CLIVE's requirements. A candidate that
satisfies all six must still be formally evaluated before adoption.

The three carried-forward design patterns (A, B, C above) are inputs to
future Block 11, Block 12, and Block 16 design work. They do not constitute
implementation decisions. Each will be absorbed as part of the respective
block's design cycle, under the standing constraints of D-002, D-003, D-006,
and D-050.

## Consequences

- Block 11 and Block 16 memory designs proceed without MemPalace.
- The six rejection reasons serve as an explicit evaluation checklist for
  any future proposal to adopt an off-the-shelf memory system.
- Pattern A reaffirms the raw-store-as-canonical principle in Block 16.
- Pattern B is a formal input to Block 12 context window design.
- Pattern C is a formal input to Block 16 retrieval interface design,
  specifically the requirement to support zone-scoped pre-filtering.
- No current sprint is blocked. The rejection does not affect any in-progress
  or scheduled implementation work.

## Related Decisions

D-003 (event bus principle — MemPalace violates this structurally),
D-006 (confirmation gate — MemPalace's unvalidated write path conflicts),
D-050 (single zone "personal" at v0.1 — pattern C maps onto this),
D-065 (Block 16 search index — pgvector; not ChromaDB),
D-068 (Block 16 raw store — S3-compatible object storage; not SQLite),
D-108 (framework adoption narrower subset — prior technology evaluation
precedent and gate conditions),
D-115 (conversation memory design — Block 11 minimal implementation),
D-128 (Block 11 full cross-session memory scope).
