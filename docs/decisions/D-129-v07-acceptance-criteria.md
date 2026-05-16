---
id: D-129
title: CLIVE v0.7 acceptance criteria — Block 11 full cross-session memory
status: Accepted
date: 2026-05-16
blocks: Block 8, Block 11, Block 16, Block 28
agents: Architect
---

## Context

v0.7 scope was approved in D-128. Six acceptance criteria are required before
v0.7 is declared done. All six must be simultaneously true.

## Acceptance Criteria

**AC-1 — SQL schema exists and is idempotent**

Two new tables created by `infrastructure/sql/init/10_v07_memory_tables.sql`:

- `clive_state.memory_entities` — entity_id uuid PK, entity_type text
  CHECK('person','date','preference','commitment','fact'), key text, value text,
  source_turn_id uuid REFERENCES conversation_turns ON DELETE SET NULL (nullable),
  embedding vector(1536), created_at timestamptz. IVFFlat cosine index on
  embedding. GRANT ALL TO clive_app.
- `clive_state.conversation_summaries` — summary_id uuid PK, conversation_id uuid,
  summary_text text, turn_range_start integer, turn_range_end integer, turn_count
  integer, embedding vector(1536), created_at timestamptz. IVFFlat cosine index on
  embedding. GRANT ALL TO clive_app.

Script is idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).
Ansible postgres-init task loop updated to include `10_v07_memory_tables.sql`.
Script runs cleanly on a fresh database and on re-run.

---

**AC-2 — Entity extraction persists to DB after each response**

`llm.py` exposes `extract_entities(user_text, assistant_text) → list[dict]` that
makes a lightweight LLM call returning structured JSON. Returns entities typed as
person / date / preference / commitment / fact, each with key and value. Returns []
on LLM error or malformed response (non-fatal).

`memory.py` exposes `store_entities(entities, source_turn_id, embeddings)` that
calls `litellm.aembedding()` (text-embedding-3-small, D-096) for each entity value
and inserts rows into `clive_state.memory_entities`. Non-fatal on DB error.

`handler.py` calls extraction and storage synchronously within the `handle_query`
coroutine, after `query.response` is emitted. Response is never delayed by
extraction.

---

**AC-3 — Semantic memory retrieval runs before context assembly**

`memory.py` exposes `retrieve_entities(query_embedding, top_k=5) → list[dict]`
that executes `ORDER BY embedding <=> $1::vector LIMIT $2` cosine similarity query
over `clive_state.memory_entities`. Returns up to 5 results as
[{entity_type, key, value, similarity_score}]. Returns [] gracefully on empty
table or DB error.

`handler.py` embeds the current user query via `llm.embed()`, then calls
`retrieve_entities()` after the spend cap check and before context assembly.
On embedding or retrieval failure: `memory_entities = []` and query continues
normally.

---

**AC-4 — Memory entities injected as Tier 3.5 in context assembly**

`context.assemble()` signature extended with `memory_entities: list[dict] = []`
parameter. `AssembledContext` dataclass includes `memory_entities` field.

Memory entities are carried through `AssembledContext.memory_entities` and
formatted by `llm.complete()` as a labelled section between conversation history
(Tier 3) and retrieved knowledge chunks (Tier 4):

```
[Memory — known facts and preferences]
- person | colleague_name: Sarah
- preference | communication_style: prefers bullet points
```

Memory tier has a 1,000-token minimum guarantee. Surplus allocation logic from
D-044 extended for three dynamic tiers (history, memory, chunks).

`assemble()` called with `memory_entities=[]` (or without the parameter) produces
output identical to the pre-v0.7 implementation. All existing `test_context.py`
tests pass unchanged.

---

**AC-5 — Memory consolidation triggers at threshold and runs post-response**

`memory.py` exposes `consolidate_if_needed(conversation_id, llm_summarise)` that:

1. Queries `clive_state.conversation_turns` for count and age.
2. Triggers when: turn count > 100 OR oldest turn > 48h old.
3. On trigger: fetches oldest 50 turns, calls `llm_summarise(turn_text)` →
   (summary_text, embedding), inserts into `clive_state.conversation_summaries`,
   DELETEs the summarised raw turns.
4. Below threshold: returns immediately (no-op).

`handler.py` calls `consolidate_if_needed()` synchronously after extraction, before
`handle_query` returns. Response emission is never delayed.

Non-fatal: exceptions are caught and logged; consolidation failure does not break
the query path.

---

**AC-6 — All tests pass; new test file with ≥8 cases**

`pytest src/query/tests/` passes with zero regressions across all existing test
files (test_context.py, test_handler.py, test_idempotency.py, test_spend_cap.py).

`test_v07_memory.py` contains ≥8 test cases covering:

| # | Case |
|---|---|
| 1 | `extract_entities` returns structured list when LLM returns valid JSON |
| 2 | `extract_entities` returns empty list when LLM returns no entities |
| 3 | `extract_entities` handles LLM error gracefully (returns []) |
| 4 | `retrieve_entities` returns top-K ordered by similarity (mocked pgvector) |
| 5 | `retrieve_entities` returns [] when DB error (no error propagated) |
| 6 | `assemble()` with memory_entities injects memory tier in context |
| 7 | `assemble()` with memory_entities=[] produces same output as before (no regression) |
| 8 | `consolidate_if_needed` creates summary row and deletes turns when count > 100 |
| 9 | `consolidate_if_needed` is a no-op when count ≤ 100 and all turns recent |
| 10 | `consolidate_if_needed` triggers on age (>48h) even when count ≤ 100 |

All tests mock DB pool and LLM client. No live DB or LLM calls in CI.

## Related Decisions

- D-128 — v0.7 scope
- D-096 — embedding model
- D-044 — context assembly priority ordering
- D-115 — Block 11 minimal baseline
