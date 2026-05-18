# D-159 — Memory entity bug fixes: timing, embedding, deduplication, acknowledgement

| Field | Value |
|---|---|
| ID | D-159 |
| Title | Memory entity bug fixes: timing, embedding, deduplication, acknowledgement |
| Status | Accepted |
| Date | 2026-05-18 |
| Blocks | Block 8 (Query/RAG), Block 11 (Memory), Block 22 (Alignment), Block 1 (Personality) |
| Recorded by | Architect |

## Context

Owner observed that a fact stated to CLIVE ("My favourite colour is red") was not
available in memory on the immediately following session. The symptom: user had to
state the fact a second time before CLIVE recalled it. Diagnosed from Telegram
transcript.

Four root causes identified:

1. **Timing race** — entity extraction runs in `handler.py` Step 15, after
   `query.response` is emitted. Because `handle_query_endpoint` dispatches the query
   as an `asyncio.create_task` and returns `{"status": "accepted"}` immediately, the
   entity extraction LLM call and storage can complete *after* the user has already
   received CLIVE's response and sent a follow-up query. The follow-up's memory
   retrieval finds an empty table.

2. **Shallow embeddings** — only the entity `value` is embedded (`"red"`), not the
   full key-value pair (`"favourite_colour: red"`). Semantic similarity between the
   bare value and an abstract memory query ("Do you remember what I told you about my
   favourite colour?") is low. While the retrieval SQL has no minimum-score filter,
   embedding depth affects ranking quality as the entity table grows.

3. **No deduplication** — `store_entities` uses a plain `INSERT` with no conflict
   handling. Repeating a fact to CLIVE stores duplicate rows. Confirmed by owner
   ("recorded twice").

4. **Response quality for user-stated facts** — CLIVE responds to "My favourite
   colour is red" as if it were a knowledge-base query, saying "I don't see any
   information about your favourite colour." Correct behaviour: acknowledge the
   statement directly. Root cause: personality document has no guidance on handling
   owner-provided information.

5. **Stale alignment document** — Block 22 Rule 2 still says "At v0.1, CLIVE can
   answer questions using its knowledge base." This predates Block 11 (cross-session
   memory, shipped v0.7). The LLM may de-prioritise memory entities as a valid
   response source.

## Decision

### Fix 1 — Move entity extraction before response emission (Bug 1)

In `src/query/query/handler.py`, the entity extraction block currently runs at
Step 15 (after `query.response` is emitted). Move it to run between Step 11
(record LLM usage) and Step 12 (emit `query.response`). Entities are then stored
before the user receives the response; by the time the user sends the next message,
the entity is guaranteed to be in `memory_entities`.

Accepted latency cost: entity extraction adds one LLM call and one embedding call
to every query (~2–4 s). Non-fatal behaviour preserved — if extraction fails, query
response is not affected.

### Fix 2 — Embed key:value instead of value-only (Bug 2)

In `src/query/query/handler.py`, change:
```python
entity_values = [e["value"] for e in entities]
```
to:
```python
entity_values = [f"{e['key']}: {e['value']}" for e in entities]
```

The stored embedding now represents "favourite_colour: red" rather than just "red",
giving meaningful semantic overlap with queries like "what's my favourite colour?"

### Fix 3 — Upsert entity storage (Bug 3)

In `src/query/query/memory.py`, change the `INSERT` in `store_entities` to an
upsert on `(entity_type, key)`. This requires a unique constraint:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS memory_entities_type_key_idx
ON clive_state.memory_entities (entity_type, key);
```

Add this to the SQL init scripts (idempotent — `CREATE UNIQUE INDEX IF NOT EXISTS`).
The INSERT becomes:
```sql
INSERT INTO clive_state.memory_entities (entity_type, key, value, source_turn_id, embedding)
VALUES ($1, $2, $3, $4, $5::vector)
ON CONFLICT (entity_type, key) DO UPDATE
  SET value = EXCLUDED.value,
      embedding = EXCLUDED.embedding,
      source_turn_id = EXCLUDED.source_turn_id
```

This also handles the case where the owner updates a preference (e.g. "my favourite
colour is now blue") — the existing row is updated rather than a duplicate added.

### Fix 4 — Personality document Memory section (Bug 4)

Add a `## Memory` section to the Block 1 personality document:

```
## Memory
When the owner tells you something about themselves — a preference, a fact,
a commitment — acknowledge it directly and briefly. Do not treat it as a
knowledge-base query. "My favourite colour is red" should receive a simple
acknowledgement, not a retrieval response. Use the [Memory] section in context
when it is present: it is reliable.
```

This is a new version of the personality document. Per D-049, activation is a
separate two-step owner action: the new version is loaded into Block 16 with
`is_active = false`, then activated via `/activate personality` +
`/confirm_activate`.

### Fix 5 — Block 22 alignment document Rule 2 update (Bug 5)

Architect updates Rule 2 to remove the stale "At v0.1" framing and reflect that
Block 11 memory is live. Handled directly; no specialist invocation required.
Details in the updated Block 22 document.

## Alternatives considered

**Keep entity extraction post-response, increase timeout on push_query_to_block8.**
Rejected: making the HTTP call synchronous would deadlock Block 13's per-conversation
queue (Block 8 emits `query.response` back to Block 13 while Block 13 is still
waiting for the original `/query` call to return).

**Filter duplicate entities in Python before INSERT.**
Rejected: database-level uniqueness constraint is the correct enforcement point.
Python check would require an additional SELECT per entity.

## Consequences

- Every query has slightly higher latency (entity extraction LLM call + embed,
  ~2–4 s, before response is delivered). Acceptable — this is personal-system
  single-owner use.
- Repeated facts update existing memory rows rather than adding duplicates.
- Semantic memory retrieval is more reliable for abstract memory queries.
- Owner must activate the new personality document version via Telegram commands
  after deployment.
- Existing duplicate rows in `memory_entities` are not cleaned up by this change.
  They are benign — top-5 retrieval is unaffected when k entities exist and
  deduplication is now enforced going forward.

## Related Decisions

- D-128 — Block 11 full cross-session memory (scope)
- D-130 — Block 11 signed off
- D-049 — System document activation two-step pattern
- D-096 — Embedding model (text-embedding-3-small, 1536-dim)
