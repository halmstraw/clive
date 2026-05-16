---
id: D-128
title: CLIVE v0.7 scope approved — Block 11 full cross-session memory
status: Accepted
date: 2026-05-16
blocks: Block 8, Block 11, Block 16
agents: Architect
---

## Context

v0.6 was signed off in D-127 (16 May 2026). The next logical step for the
intelligence layer is completing Block 11 (Memory Management). The v0.4 minimal
baseline (D-115) stores raw conversation turns in `clive_state.conversation_turns`
and injects the last N turns into Block 8 context. That baseline is functional but
does not support cross-session recall, entity-level fact retention, or graceful
handling of long conversation histories.

## Options Considered

**A. Extend Block 11 with full memory capabilities in one version** — consolidation,
extraction, and semantic retrieval delivered together. Makes memory coherent as a
system; all three capabilities are interdependent (extraction feeds retrieval;
consolidation keeps the turns table manageable).

**B. Incremental delivery** — consolidation only in v0.7, extraction in v0.8,
retrieval in v0.9. Lower risk per version but leaves Block 11 in an incomplete
state for multiple versions, and each intermediate state is of limited value.

## Decision

Option A. v0.7 delivers Block 11 full cross-session memory in three additions:

**1. Memory consolidation** — Old turns (>100 in conversation OR oldest turn >48h)
are compressed into a summary row in `clive_state.conversation_summaries` and the
raw turns are pruned. Consolidation runs synchronously within the `handle_query`
coroutine after `query.response` is emitted. No background worker required at v0.7.

**2. Entity / fact extraction** — After each query/response pair, Block 8 makes a
lightweight LLM extraction call on the turn text. Named entities typed as person,
date, preference, commitment, or fact are stored in a new
`clive_state.memory_entities` table with 1536-dim embeddings (D-096,
text-embedding-3-small via LiteLLM).

**3. Semantic memory retrieval** — The Block 8 query handler embeds the current
query and performs a pgvector cosine similarity search over
`clive_state.memory_entities` before context assembly. Top-5 results are injected
as a new Tier 3.5 in context (after conversation history, before retrieved knowledge
chunks), with a 1,000-token minimum guarantee.

All three capabilities are internal to Block 8 — no new events required for the
retrieval path (D-003 compliant). Memory DB access uses the existing `clive_app`
pool, consistent with the v0.6 `llm_usage` write pattern.

## Rationale

Consolidation, extraction, and retrieval are not independently valuable — you need
all three for meaningful cross-session memory. Extraction without retrieval is waste.
Retrieval without extraction is empty. Consolidation without extraction leaves
long-term memory unstructured. Delivering together is correct.

## Design decisions locked by this scope

| Parameter | Value | Rationale |
|---|---|---|
| Consolidation turn threshold | >100 turns | Balances memory vs. retrieval overhead |
| Consolidation age threshold | >48h | Cross-session boundary; day-old turns should be consolidated |
| Consolidation batch size | 50 turns per pass | Keeps LLM summarisation prompt tractable |
| Entity types | person, date, preference, commitment, fact | Covers the core owner-relevant fact categories |
| Embedding model | text-embedding-3-small, 1536-dim (D-096) | Consistent with knowledge chunk embeddings |
| Semantic retrieval top-K | 5 | Keeps memory tier token cost predictable |
| Memory tier minimum | 1,000 tokens | Lower than history/retrieval minimums; entity values are short |
| Extraction model | CLIVE_LLM_MODEL (same as query) | No separate extraction model at v0.7; keep simple |
| Memory DB access | Direct clive_app pool | Internal to Block 8; same pattern as llm_usage (D-125) |

## Consequences

- Two new DB tables required: `clive_state.memory_entities` and
  `clive_state.conversation_summaries`. Idempotent SQL script
  `infrastructure/sql/init/10_v07_memory_tables.sql` added to Ansible init loop.
- `src/query/query/memory.py` is the new Block 11 implementation module.
- `context.py`, `handler.py`, and `llm.py` extended to wire memory into the
  query path.
- Extraction and consolidation are post-response operations — they never delay
  the owner's response.
- All memory functions are non-fatal: they catch exceptions, log, and return
  gracefully. A DB or embedding failure degrades memory but does not break queries.

## Related Decisions

- D-115 — Block 11 minimal baseline (conversation turns)
- D-096 — Embedding model (text-embedding-3-small, 1536-dim)
- D-127 — v0.6 signed off
- D-129 — v0.7 acceptance criteria
