# Block 12 — Context Window Policy

*Produced: 2026-05-17. Wave: v0.9 design and documentation only. No source code
changes in this wave. Source code enforcement is Wave 2-B.*

*Governing decisions: D-044 (dynamic allocation with priority ordering),
D-128 (memory entities as Tier 3.5), D-137 (tool registry integration).*

---

## 1. Purpose

Block 12 is the context window policy for CLIVE. It defines the rules that
govern what enters the LLM context window on every query, in what priority
order, at what token allocation, and how conflicts between competing content
are resolved when space is limited.

Block 8 (Query/RAG) assembles the context and calls the LLM. Block 12 is the
policy that governs how Block 8 does that assembly. They are separate concerns:
Block 8 is a service; Block 12 is a specification of invariants, budgets, and
tier ordering that Block 8 must satisfy. This separation matters because the
same policy must govern any future surface, worker, or service that produces
LLM calls — not only Block 8's primary query handler. Keeping the policy
explicit and separate makes it auditable, evolvable, and enforceable
independently of Block 8's implementation.

---

## 2. Total Context Budget

**`TOTAL_BUDGET = 98,000 tokens`** (defined in `src/query/query/context.py`).

This budget covers all injected text that passes through the context assembly
function (`ctx.assemble()`). It includes:

- Tier 1: the personality document
- Tier 2: the alignment rules document
- Tier 3: conversation history (selected turns)
- Tier 3.5: memory entities retrieved from Block 11
- Tier 4: knowledge chunks retrieved from Block 16

The budget does **not** include:

- The live user query text — passed to the LLM directly, not counted
- The tool registry section — injected by the LLM layer (`llm.py`) after
  context assembly, outside this budget (see Known Implementation Gaps)

**Derivation:** The model in production use supports 200k tokens. The system
operates against a conservative 100k target. Approximately 2,000 tokens are
reserved for the live user query text and associated formatting overhead,
yielding `TOTAL_BUDGET = 98,000`. This reservation is approximate; no named
constant exists for the 2,000-token reserve (see Known Implementation Gaps).

---

## 3. Priority Tiers

Five content tiers exist in the current implementation. Tiers 1 and 2 are
fixed-cost (always included in full). Tiers 3, 3.5, and 4 are variable and
share the remaining budget after fixed costs are deducted, each with a
guaranteed minimum allocation.

---

### Tier 1 — Personality Document

| Property | Value |
|---|---|
| Source | Block 16 (via orchestrator-mediated retrieval, D-043) |
| Token allocation | Full document, no cap |
| Minimum | Entire document always included |
| Truncation | Never truncated |
| Overflow | System is not expected to reach this state; if Tier 1 + Tier 2 consume the entire budget minus minimum guarantees, remaining budget is set to the sum of minimums (see Allocation Algorithm) |
| Injection position | First section of the LLM system prompt |

The personality document is the primary voice and behavioural identity of
CLIVE (D-005, D-039). It is always present. Omitting or truncating it would
produce a fundamentally different system. Tier 1 is the first fixed cost
deducted from `TOTAL_BUDGET`.

---

### Tier 2 — Alignment Rules Document

| Property | Value |
|---|---|
| Source | Block 16 (via orchestrator-mediated retrieval, D-043) |
| Token allocation | Full document, no cap |
| Minimum | Entire document always included |
| Truncation | Never truncated |
| Overflow | Same handling as Tier 1 |
| Injection position | Second section of the LLM system prompt, after Tier 1 |

The alignment rules document governs what CLIVE is and is not permitted to do
at query time (D-037). It is always present. Tier 2 is the second fixed cost
deducted from `TOTAL_BUDGET`.

---

### Tier 3 — Conversation History

| Property | Value |
|---|---|
| Source | Event payload (`conversation_history` field from Block 13) |
| Token floor | `MIN_HISTORY_TOKENS = 2,000` |
| Token allocation | Floor plus proportional share of remaining surplus (see Allocation Algorithm) |
| Truncation rule | Oldest turns dropped first; most-recent turns preserved |
| Injection position | LLM message thread, before the final user message (oldest→newest ordering) |

Conversation history gives CLIVE within-session continuity. When the history
exceeds its allocation, the truncation function (`_truncate_history`) iterates
in reverse (most-recent-first) and accumulates turns until the budget is
exhausted, preserving the most recent context.

---

### Tier 3.5 — Memory Entities

| Property | Value |
|---|---|
| Source | Block 11 via semantic retrieval (D-128) |
| Token floor | `MIN_MEMORY_TOKENS = 1,000` |
| Token allocation | Floor plus proportional share of remaining surplus (see Allocation Algorithm) |
| Truncation rule | Lowest-similarity entities dropped; highest-similarity entities preserved |
| Injection position | Within the final user message, before Tier 4, prepended to the live query |

Memory entities are facts, preferences, commitments, and named entities
extracted from prior sessions (D-128). Up to 5 entities are retrieved per
query (top-k cosine similarity, Block 11). Entities arrive in similarity order
(closest-first). When the entity set exceeds its allocation, the truncation
function (`_truncate_memory_entities`) iterates forward and stops when the
budget is exhausted, preserving the highest-similarity entities. A section
header (`[Memory — known facts and preferences about you]`) is included in the
token count.

Tier 3.5 was introduced in v0.7 (D-128). Calling context assembly with an
empty or absent memory entities list produces output identical to pre-v0.7
behaviour.

---

### Tier 4 — Retrieved Knowledge Chunks

| Property | Value |
|---|---|
| Source | Block 16 knowledge base (via orchestrator-mediated retrieval, D-043) |
| Token floor | `MIN_RETRIEVAL_TOKENS = 4,000` |
| Token allocation | Residual after Tier 3 and Tier 3.5 allocations are deducted from remaining budget |
| Truncation rule | Lowest-relevance chunks dropped; highest-relevance chunks preserved |
| Injection position | Within the final user message, after Tier 3.5, before the live query |

Up to 20 chunks are retrieved per query (configurable at call site). Chunks
arrive in relevance order (highest-first). The truncation function
(`_truncate_chunks`) iterates forward and stops when the budget is exhausted,
preserving the highest-relevance chunks. Each chunk is prefixed with its
source attribution (`[Source: <attribution>]`).

Tier 4 receives the residual: `remaining - history_alloc - memory_alloc`.
This means if surplus is fully consumed by Tiers 3 and 3.5, Tier 4 still
receives its floor (`MIN_RETRIEVAL_TOKENS`).

---

### Tool Registry Section (Not a Budgeted Tier)

The tool registry section (name and description of available tools from Block
17) is injected by the LLM layer (`llm.py`) as a third section of the system
prompt, after Tier 2. It is **not tracked by `context.py`** and **not counted
against `TOTAL_BUDGET`**. The `permission_scope` field is never exposed to the
LLM — only `tool_name` and `description` are included (D-138).

This section's token cost is outside the budgeted tiers. See Known
Implementation Gaps.

---

## 4. Allocation Algorithm

The following steps describe exactly how `ctx.assemble()` (in
`src/query/query/context.py`) consumes the budget, tier by tier.

**Step 1 — Deduct fixed costs (Tiers 1 and 2)**

```
fixed_cost = tokens(personality) + tokens(alignment_rules)
remaining  = TOTAL_BUDGET - fixed_cost
```

Both documents are included in full, unconditionally.

**Step 2 — Total minimum guarantee**

```
total_min = MIN_HISTORY_TOKENS + MIN_MEMORY_TOKENS + MIN_RETRIEVAL_TOKENS
          = 2,000 + 1,000 + 4,000
          = 7,000 tokens
```

**Step 3 — Pathological overflow guard**

If `remaining < total_min` (i.e. Tiers 1 and 2 have consumed nearly all of
`TOTAL_BUDGET`), the remaining budget is overridden to `total_min`:

```
if remaining < total_min:
    remaining = total_min
```

This preserves the minimum guarantees for Tiers 3, 3.5, and 4. In this case
the total tokens sent to the LLM will exceed `TOTAL_BUDGET`. This is the
pathological path; normal system document sizes are well within the budget.

**Step 4 — Compute surplus**

```
surplus = max(0, remaining - total_min)
```

Surplus is the budget available above the combined floor of all three variable
tiers.

**Step 5 — Estimate surplus demand from each tier**

```
history_surplus_needed = max(0, tokens(history_text) - MIN_HISTORY_TOKENS)
memory_surplus_needed  = max(0, tokens(memory_text)  - MIN_MEMORY_TOKENS)
chunks_surplus_needed  = max(0, tokens(chunks_text)  - MIN_RETRIEVAL_TOKENS)
total_surplus_needed   = sum of the above three
```

**Step 6 — Proportional surplus allocation**

If any tier needs more than its floor (`total_surplus_needed > 0`):

```
history_alloc = MIN_HISTORY_TOKENS + floor(surplus × history_surplus_needed / total_surplus_needed)
memory_alloc  = MIN_MEMORY_TOKENS  + floor(surplus × memory_surplus_needed  / total_surplus_needed)
chunks_alloc  = remaining - history_alloc - memory_alloc
```

Tier 4 receives the residual to avoid rounding accumulation.

If no tier needs more than its floor (`total_surplus_needed == 0`):

```
history_alloc = MIN_HISTORY_TOKENS
memory_alloc  = MIN_MEMORY_TOKENS
chunks_alloc  = remaining - history_alloc - memory_alloc
```

**Step 7 — Truncate each tier to its allocation**

- Tier 3 (history): `_truncate_history(conversation_history, history_alloc)`
  — iterates newest-first, drops oldest
- Tier 3.5 (memory): `_truncate_memory_entities(memory_entities, memory_alloc)`
  — iterates highest-similarity-first, drops lowest
- Tier 4 (chunks): `_truncate_chunks(retrieved_chunks, chunks_alloc)`
  — iterates highest-relevance-first, drops lowest

**Step 8 — Assemble and return**

`AssembledContext` carries:
- `personality` (Tier 1, full)
- `alignment_rules` (Tier 2, full)
- `conversation_history` (Tier 3, truncated)
- `memory_entities` (Tier 3.5, truncated)
- `retrieved_chunks` (Tier 4, truncated)
- `token_estimate = fixed_cost + history_alloc + memory_alloc + chunks_alloc`

**Step 9 — LLM layer injection (outside budget)**

`llm.complete()` receives the assembled context and additionally:
- The live user query (not budgeted)
- The available tools snapshot from Block 17 (not budgeted)

The LLM call is constructed as:

```
System prompt = {Tier 1} \n\n---\n\n {Tier 2} \n\n---\n\n {tool_list}
Messages      = [{Tier 3 turns, oldest→newest},
                 {role: user, content: [{Tier 3.5}] --- [{Tier 4}] --- Query: {live query}}]
```

---

## 5. Invariants

The following rules hold on every query, regardless of content volume:

**I-1 — Tier 1 and Tier 2 are always present and never truncated.**
The personality document and alignment rules document are included in full in
every LLM call. No query may proceed without them.

**I-2 — The live user query is not counted against the context budget.**
`user_input` is passed directly to `llm.complete()` and appended to the final
user message. It does not pass through `ctx.assemble()` and is not tracked by
`TOTAL_BUDGET`.

**I-3 — Each variable tier has a guaranteed minimum allocation.**
Tiers 3, 3.5, and 4 each have an absolute floor:
`MIN_HISTORY_TOKENS = 2,000`, `MIN_MEMORY_TOKENS = 1,000`,
`MIN_RETRIEVAL_TOKENS = 4,000`. No tier can be squeezed below its floor by
surplus demand from another tier.

**I-4 — Truncation is deterministic and priority-ordered.**
- History: most recent turns preserved; oldest dropped
- Memory entities: highest-similarity entities preserved; lowest dropped
- Chunks: highest-relevance chunks preserved; lowest dropped

No random selection. Same input always produces same output.

**I-5 — No tier silently exceeds its allocation.**
Each truncation function checks token cost against its budget before
appending content. Any item that would cause the tier to exceed its allocation
is dropped rather than partially included (chunks and turns are atomic units).

**I-6 — The LLM never sees `permission_scope`.**
The tool registry injection in `llm.py` exposes only `tool_name` and
`description` for each tool. The `permission_scope` field is deliberately
excluded. This invariant is enforced in `_build_tools_section()` (D-138).

**I-7 — Empty memory entities produce identical output to pre-v0.7 behaviour.**
When `memory_entities` is `[]` or omitted, `ctx.assemble()` and `llm.complete()`
produce output identical to pre-v0.7 (D-128 AC-4 regression requirement).

---

## 6. Future Notes

The following are **out of scope** for the current policy and are not governed
by this document:

**6.1 — Dynamic tier reweighting by query type.**
The current allocation is uniform: every query uses the same minimum floors
and the same proportional surplus distribution. A future policy may allow
query-type signals (e.g. action intent, factual lookup vs. reflection) to
shift allocations — for example, suppressing memory entities for action-intent
queries where retrieved context matters more. This is not designed or
scheduled.

**6.2 — Per-surface budget differences.**
At v0.11, a second surface (web dashboard, D-136) will be introduced. Different
surfaces may carry different effective budgets (e.g. richer history on
desktop, leaner on mobile). The current policy assumes a single surface
(Telegram, D-061) and a single `TOTAL_BUDGET` constant. Per-surface budget
variants will require a policy revision.

**6.3 — Worker context assembly (Block 10).**
Block 10 workers are separate entities deployed on the event bus (D-040).
When workers make LLM calls, those calls are not governed by this policy.
Block 10 context assembly policy is out of scope for Block 12 until Block 10
is activated. Any worker that requires personality or alignment context must
define its own context budget in its worker specification, consistent with the
invariants in Section 5.

**6.4 — Response token budget.**
The LLM completion call uses `max_tokens = 2048` (set in `llm.py`). This is
a separate cap on output length and is not part of the context input budget
tracked here. The 2,000-token approximate reserve in `TOTAL_BUDGET` is
related but not identical: the reserve covers user query formatting overhead
as well as anticipating response space. These are not formally linked by a
named constant.

---

## Known Implementation Gaps

The following gaps exist between this policy and the current source code. None
are defects that affect correctness in normal operating conditions. They are
flagged here for resolution in Wave 2-B (source code enforcement).

**Gap 1 — Token estimation uses character count, not a tokeniser.**

```python
CHARS_PER_TOKEN = 4
def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN
```

The `len(text) // 4` approximation can under- or over-estimate true token
count by 20–30% depending on content (code, unicode, punctuation-heavy text).
This means tiers may in practice consume more or fewer tokens than their
allocated budgets. Wave 2-B should replace this with a real token counter
(e.g. a tokenisation library appropriate to the model in use, per D-002 — no
technology choice in this document).

**Gap 2 — Tool registry section is not tracked by the context budget.**

The `_build_tools_section()` function in `llm.py` appends the tool list to
the system prompt after context assembly. This text is not counted against
`TOTAL_BUDGET`. There is no cap on tool section size. As the tool registry
grows, the actual tokens sent to the LLM will drift above `token_estimate`
without any enforcement or logging.

Wave 2-B should either: (a) include the tool section in `ctx.assemble()` with
its own tier and allocation, or (b) define a named token cap for the tool
section and enforce it in `_build_tools_section()`.

**Gap 3 — No named constant for the 2,000-token query-and-overhead reserve.**

`TOTAL_BUDGET = 98,000` is derived as (100k operating target) − (~2k
reserve), but the 2,000-token reserve is not a named constant and is not
enforced. The relationship between `TOTAL_BUDGET` and the model's true context
limit is documented only in a comment. Wave 2-B should introduce a named
constant (e.g. `QUERY_OVERHEAD_RESERVE`) and derive `TOTAL_BUDGET` from it
explicitly.

**Gap 4 — Pathological overflow does not fail; it silently expands the budget.**

The code comment says "Pathological case: personality/alignment docs are
enormous." When this occurs, the budget is silently expanded to accommodate
minimum tier guarantees:

```python
if remaining < total_min:
    remaining = total_min
```

No error is raised, no alert is emitted, and `token_estimate` in the returned
`AssembledContext` will be inflated above `TOTAL_BUDGET`. In practice, system
document sizes are well below the threshold where this triggers. However,
the invariant documented in Section 5 (I-1: Tier 1 and Tier 2 always fit)
relies on this being a non-event. Wave 2-B should add observability (a
log warning or metric counter) so that if this path is ever triggered it is
visible.

**Gap 5 — Tier 4 receives residual allocation, not a proportional share.**

```python
chunks_alloc = remaining - history_alloc - memory_alloc
```

Tier 4 is not allocated proportionally from the surplus. It receives whatever
is left after Tiers 3 and 3.5 take their shares. Due to integer truncation in
the proportional calculations for Tiers 3 and 3.5, Tier 4 may receive
slightly more or less than a strict proportional share. This is intentional
(to avoid rounding accumulation) but is undocumented as policy. Wave 2-B
should confirm or revise this as the explicit policy choice.
