# Event Bus Contract — Reference

*Supporting file for the event-schema skill. Load when designing block
interfaces or reviewing event definitions for completeness.*

---

## The Contract in Full

### Rule 1 — No direct block-to-block communication (D-003)

No block may call, query, write to, or read from another block directly.
Every interaction between blocks is mediated by Block 13 (Central Orchestrator)
via the event bus. This rule has no exceptions.

### Rule 2 — Events are named after what happened

Events describe completed facts, not instructions. `INGESTION_COMPLETE` is
correct. `PROCESS_NOW` is not. The emitting block does not instruct the
consuming block — it reports what happened. Block 13 routes the event to
whoever needs to act on it.

### Rule 3 — Every event has exactly one emitter

Events have one source. If two blocks both need to signal the same thing,
they emit two separate events. There is no shared event ownership.

### Rule 4 — All events are logged

Block 13 passes the full event stream to Block 25 (Observability). No event
is unlogged. This is how alignment monitoring, debugging, and the Evolution
Engine fitness signals all work. If your design has events that "don't need
logging," reconsider the design.

### Rule 5 — Every event has a failure path

If an event cannot be routed (Block 13 failure) or cannot be consumed
(consuming block failure), there must be a defined behaviour. Silent failure
is not a valid failure path.

---

## Worked Examples

### Example 1 — Ingestion to Processing

Scenario: A new document has been ingested by Block 14. It needs to be
processed by Block 15.

```
EVENT: INGESTION_COMPLETE
  Emitted by:   Block 14 — Ingestion
  Consumed by:  Block 15 — Processing
  Trigger:      A source document has passed deduplication check and
                been written to the raw store in Block 16.
  Payload:      source_id, content_hash, raw_store_reference,
                zone_assignment, ingestion_timestamp, source_credibility_score
  On failure:   If Block 15 does not acknowledge within timeout, Block 13
                emits PROCESSING_STALLED to Block 25 and retries up to
                N times (N TBD). Owner alerted via Block 4 if unresolved.
  Notes:        zone_assignment is set at ingestion time and must not be
                modified by Block 15. Zone boundary enforcement is
                Block 23's responsibility at the storage write layer.
```

### Example 2 — Query triggering retrieval

Scenario: Block 8 (Query/RAG) needs chunks from Block 16 (Storage) to
answer a query. It cannot call Block 16 directly.

```
EVENT: RETRIEVAL_REQUESTED
  Emitted by:   Block 8 — Query/RAG
  Consumed by:  Block 16 — Storage
  Trigger:      Block 8 has parsed a query and determined what knowledge
                is needed to synthesise a response.
  Payload:      query_id, query_embedding, zone_scope, max_chunks,
                retrieval_strategy_hint, conversation_id
  On failure:   If Block 16 does not respond within timeout, Block 8
                emits RETRIEVAL_FAILED to Block 13. Block 13 routes to
                Block 4 to surface an error to the owner.
  Notes:        zone_scope enforces Block 7 boundaries — Block 16 must
                not return chunks from zones outside zone_scope.
                retrieval_strategy_hint is advisory — Block 16 may
                override based on index state.

EVENT: RETRIEVAL_COMPLETE
  Emitted by:   Block 16 — Storage
  Consumed by:  Block 8 — Query/RAG
                Block 12 — Context Window Management
  Trigger:      Block 16 has completed chunk retrieval for a query_id.
  Payload:      query_id, chunks (list), retrieval_latency_ms,
                chunks_considered, chunks_returned, zone_scope_honoured
  On failure:   If Block 8 does not acknowledge, Block 16 emits
                RETRIEVAL_ACKNOWLEDGEMENT_TIMEOUT to Block 13.
  Notes:        Block 12 receives this event to manage context window
                allocation before chunks are passed to the LLM.
                zone_scope_honoured must be true — if Block 16 cannot
                honour zone scope, it must emit RETRIEVAL_ZONE_VIOLATION
                to Block 13 instead of completing retrieval.
```

### Example 3 — Action requiring confirmation

Scenario: Block 9 (Action Layer) has a pending action that needs owner
confirmation before execution.

```
EVENT: ACTION_PENDING_CONFIRMATION
  Emitted by:   Block 9 — Action Layer
  Consumed by:  Block 4 — Interface/Egress
                Block 5 — Sync/State Layer
  Trigger:      Block 9 has received an action request and staged it
                pending explicit owner confirmation.
  Payload:      action_id, action_type, action_description,
                affected_system, consequence_summary, requested_by,
                timeout_seconds, zone
  On failure:   If Block 4 cannot deliver the confirmation request
                to any surface, action_id remains pending. Block 13
                emits CONFIRMATION_DELIVERY_FAILED to Block 25.
                Action is NOT executed. Owner alerted on reconnect.
  Notes:        timeout_seconds counts from first successful delivery
                to any surface. Timeout equals rejection — Block 9
                must emit ACTION_REJECTED on timeout, never
                ACTION_EXECUTED. This is D-006 and is non-negotiable.

EVENT: ACTION_CONFIRMED
  Emitted by:   Block 4 — Interface/Egress
  Consumed by:  Block 9 — Action Layer
  Trigger:      Owner has explicitly confirmed a pending action on
                any surface.
  Payload:      action_id, confirmed_by_surface, confirmation_timestamp
  On failure:   If Block 9 does not receive within timeout, treat as
                rejection. Block 9 emits ACTION_REJECTED.
  Notes:        Confirmation must be explicit — no inferred or
                timeout-based confirmation.

EVENT: ACTION_REJECTED
  Emitted by:   Block 9 — Action Layer
                Block 4 — Interface/Egress (timeout path)
  Consumed by:  Block 25 — Observability
                Block 4 — Interface/Egress (notify owner)
  Trigger:      Owner explicitly rejected, or timeout elapsed with
                no confirmation.
  Payload:      action_id, rejection_reason (explicit / timeout),
                rejection_timestamp
  On failure:   Rejection is logged regardless. Block 25 must
                acknowledge. If Block 25 is unavailable, log locally
                and retry on reconnect.
  Notes:        Rejection is the safe default. The audit log entry
                for a rejected action is immutable.
```

### Example 4 — Worker completing a task

Scenario: A background worker (Block 10) has completed a scheduled task
and needs to report the outcome.

```
EVENT: WORKER_TASK_COMPLETE
  Emitted by:   Block 10 — Workers/Background Agents
  Consumed by:  Block 4 — Interface/Egress
                Block 25 — Observability
                Block 13 — Orchestrator (for scheduling next run)
  Trigger:      A worker has completed its scheduled task execution.
  Payload:      worker_id, task_id, outcome (success / partial / failed),
                summary, duration_ms, actions_taken (list of action_ids),
                next_scheduled_run
  On failure:   Block 13 retries delivery to Block 4 and Block 25.
                If Block 4 is unavailable, summary is queued for next
                available surface.
  Notes:        actions_taken references action_ids already routed
                through Block 9 confirmation gate. Workers do not
                report actions that bypassed the gate — those cannot
                exist.
```

---

## Event Naming Conventions

| Pattern | Use for |
|---|---|
| `[THING]_COMPLETE` | Successful completion of a process |
| `[THING]_REQUESTED` | A block is asking for something |
| `[THING]_FAILED` | A process failed |
| `[THING]_REJECTED` | An explicit rejection (confirmation gate) |
| `[THING]_STALLED` | A process is stuck and needs attention |
| `[THING]_PENDING_[STATE]` | A thing is waiting for something |
| `[THING]_VIOLATION` | A constraint was breached (zone, alignment) |
| `[THING]_TIMEOUT` | A time limit was reached |

---

## Cross-Block Dependency Flags

When you define an event and realise the consuming block belongs to a
different agent's block group, flag it explicitly:

```
CROSS-BLOCK DEPENDENCY FLAG
Event: [EVENT_NAME]
Emitted by: Block N ([your block group])
Consumed by: Block M ([different agent's block group])
Flag for: [Agent name] to confirm consumption requirements
Status: Pending cross-agent review
```

Raise this flag in your output. The Architect will coordinate the review.
Do not assume the other agent's block can consume your event without
confirming the interface.
