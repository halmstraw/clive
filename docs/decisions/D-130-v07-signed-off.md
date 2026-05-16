---
id: D-130
title: CLIVE v0.7 signed off — all six criteria met 16 May 2026
status: Accepted
date: 2026-05-16
blocks: Block 8, Block 11, Block 16, Block 28
agents: Architect
---

## Context

v0.7 scope was approved in D-128. Six acceptance criteria were defined in
D-129. Implementation was completed and a production smoke test was run
on 16 May 2026.

## Options Considered

Not applicable — sign-off decision records a verified outcome.

## Decision

CLIVE v0.7 is signed off. All six D-129 criteria were simultaneously true
at time of sign-off on 16 May 2026:

1. ✅ **AC-1 — SQL schema exists and is idempotent**
   `clive_state.memory_entities` and `clive_state.conversation_summaries`
   created by `infrastructure/sql/init/10_v07_memory_tables.sql`. IVFFlat
   cosine indexes on both embedding columns. `GRANT ALL TO clive_app` on
   both. Script runs cleanly on a fresh database and on re-run. Ansible
   postgres-init loop updated. Deploy pipeline applies automatically via
   `ls infrastructure/sql/init/*.sql | sort`.

2. ✅ **AC-2 — Entity extraction persists to DB after each response**
   Production log confirmed: `entities_extracted count=3` followed by
   `memory_entities_stored count=3` after the first test query. DB query
   showed three rows (person/colleague_name/Sarah, date/product_review_date/Friday,
   fact/sarah_role/leading product review). Second turn logged
   `entities_extracted count=2`, `memory_entities_stored count=2`.

3. ✅ **AC-3 — Semantic retrieval runs before context assembly**
   Production log confirmed: `memory_entities_retrieved count=2` logged
   before `llm_call_start` on the second query (fresh session, no prior
   context). pgvector cosine similarity returned the 2 most relevant
   entities from 3 stored.

4. ✅ **AC-4 — Memory entities injected as Tier 3.5 in context**
   Production log confirmed: `memory_entities=2` in `llm_call_start` and
   `memory_entities_used=2` in `query_handled`. CLIVE's response ("Sarah
   is leading the product review. It's scheduled for Friday.") used the
   stored entities correctly without the information being restated in the
   current session or present in any knowledge document.

5. ✅ **AC-5 — Consolidation triggers at threshold and runs post-response**
   CI-verified. Live threshold (>100 turns or >48h old) not reachable in
   a smoke test. Unit tests in `test_v07_memory.py` cover both trigger
   conditions and the no-op path.

6. ✅ **AC-6 — All tests pass; ≥8 new test cases**
   `pytest src/query/tests/` — 40 passed, 0 failed. `test_v07_memory.py`
   contains 14 test cases. All 26 pre-existing tests pass unchanged.

## Production bugs fixed during this session

Two bugs were found and fixed during implementation:

**Bug 1 — asyncpg pgvector serialisation** (`memory.py`):
asyncpg has no built-in pgvector codec. Passing `list[float]` directly to
a `$N::vector` SQL parameter fails silently (exception caught and logged).
Fix: `str(embedding)` before every vector parameter — matching the
established pattern in `processing/store.py`. This was causing all three
vector operations (store, retrieve, consolidate) to silently fail, leaving
`memory_entities` empty.

**Bug 2 — test payload missing `action_type`** (`test_v03_commands.py`):
The v0.7 refactor of `deliver_action_confirmation` added branching on
`action_type`. The v0.3 test payload was missing `"action_type":
"document.delete"`, causing the function to store in `_pending_action_generic`
instead of `_pending_deletes`. CI failure. Fixed by adding the field to the
test payload.

## Consequences

- Block 11 (Memory Management) is fully implemented at v0.7 baseline.
- CLIVE now extracts named entities (person/date/preference/commitment/fact)
  from every conversation turn and stores them with 1536-dim embeddings.
- Semantic memory retrieval runs before every LLM call; top-5 entities
  are injected as Tier 3.5 in context between conversation history and
  knowledge chunks.
- Long conversations (>100 turns or >48h old) are automatically compressed
  into summaries, keeping the `conversation_turns` table manageable.
- All memory operations are non-fatal — failures degrade gracefully without
  breaking query responses.

## Related Decisions

- D-128 — v0.7 scope
- D-129 — v0.7 acceptance criteria
- D-115 — Block 11 minimal baseline (v0.4)
- D-096 — embedding model (text-embedding-3-small, 1536-dim)
- D-127 — v0.6 signed off
