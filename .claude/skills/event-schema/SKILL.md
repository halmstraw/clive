---
name: event-schema
description: >
  Use when defining how blocks communicate through the Central Orchestrator
  (Block 13). Triggers on: "define event", "event schema", "block interface",
  "what events does block N emit", "inter-block communication", or any
  design work that involves one block sending data to another. All inter-block
  communication in CLIVE routes through Block 13 via events — no direct
  block-to-block calls. This skill enforces that contract and provides the
  standard schema format.
---

# Event Schema

## Purpose

In CLIVE, no block communicates directly with another block (D-003).
All inter-block communication routes through the Central Orchestrator
(Block 13) via events. This skill defines the standard format for
documenting those events so that every agent produces consistent,
composable interface specifications.

See `reference/event-bus-contract.md` for the full contract and examples.

---

## The Event Bus Contract (Summary)

- Every block **emits** events when something happens inside it
- Every block **subscribes** to events it needs to act on
- Block 13 (Orchestrator) routes all events — it sees everything
- No block calls another block directly — ever
- All events are logged (Block 25 receives the full event stream from Block 13)

If you find yourself writing "Block X calls Block Y" — stop. Rewrite it as
"Block X emits event E, Block 13 routes it to Block Y."

---

## Standard Event Definition Format

Use this format for every event you define. All fields are required.

```
EVENT: [EVENT_NAME]
  Emitted by:   Block N — [Block Name]
  Consumed by:  Block N — [Block Name]
                Block N — [Block Name]  (list all consumers)
  Trigger:      [What causes this event to be emitted — one sentence]
  Payload:      [What data the event carries — list fields]
  On failure:   [What happens if routing or consumption fails]
  Notes:        [Any constraints, sequencing requirements, or open questions]
```

### Field guidance

**EVENT_NAME** — Use SCREAMING_SNAKE_CASE. Name it after what happened,
not what should happen next. `INGESTION_COMPLETE` not `PROCESS_THIS`.

**Emitted by** — Exactly one block. Events have one source.

**Consumed by** — One or more blocks. List all of them. If a consumer is
not yet known, write `TBD — flag for Architect`.

**Trigger** — The condition inside the emitting block that causes the event.
Be specific: "When a new document has passed deduplication check" not
"When ingestion happens."

**Payload** — List the fields the event carries. Do not include implementation
types (no `string`, `int`, `UUID`) during requirements — describe the data
in plain terms. Example: `source_id, content_hash, zone_assignment, timestamp`.

**On failure** — What Block 13 or the consuming block does if the event
cannot be routed or processed. Silence is not acceptable — every failure
path must be named.

**Notes** — Sequencing constraints (this event must follow event X),
ordering guarantees needed, open questions, or alignment flags.

---

## Block Interface Specification Format

When documenting all events for a block group, use this structure:

```
## Block N — [Block Name] — Event Interface

### Events Emitted

[EVENT_NAME definition]
[EVENT_NAME definition]

### Events Consumed

[EVENT_NAME definition]
[EVENT_NAME definition]

### Open Interface Questions

- [Any unresolved questions about this block's events]
```

---

## Common Mistakes

**Direct call disguised as an event**
Wrong: "Block 8 retrieves chunks from Block 16."
Right: "Block 8 emits RETRIEVAL_REQUESTED. Block 13 routes it to Block 16.
Block 16 emits RETRIEVAL_COMPLETE with the chunks. Block 13 routes it back
to Block 8."

**Missing failure path**
Every event definition must include `On failure`. If you don't know what
failure looks like yet, write "TBD — flag for Architect" and raise it.

**Payload with implementation types**
Wrong payload: `chunk_id: UUID, content: string, score: float`
Right payload: `chunk_id, content, relevance_score, zone`

**Consumers not listed**
If you don't know all consumers yet, list the known ones and add
"TBD — additional consumers may exist, flag for Architect review."

---

## Checking Your Design Against D-003

Before finalising any block interface, run this check:

1. For every interaction between your block and another block:
   - Is it expressed as an emitted event with a named payload? ✓
   - Does Block 13 sit between the two blocks? ✓
   - Is there a failure path defined? ✓

2. Is there any sentence in your design that says "Block X calls / queries /
   writes to / reads from Block Y directly"?
   - If yes: rewrite it as events before proceeding

3. Does Block 25 (Observability) receive this event stream automatically
   via Block 13?
   - It should. If your design has a block reporting directly to Block 25,
     rewrite it — Block 13 carries the full event stream to Block 25.
