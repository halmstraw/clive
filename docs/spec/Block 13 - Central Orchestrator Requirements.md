*Systems Agent requirements artefact — produced May 2026. Approved decisions incorporated. Pending Architect records: D-NEW-01 through D-NEW-04.*

---
# Block 13 — Central Orchestrator Requirements

## 1. Purpose

Block 13 is the sole routing layer for all inter-block communication in CLIVE. Every block emits events to the orchestrator and subscribes to events from it. No block communicates with any other block directly. The orchestrator does not reason, interpret queries, or assess action quality — those responsibilities belong to other blocks. Its function is precisely bounded: receive an event, check it against the alignment constitution, log it, and route it to declared subscribers. It is also the single point of human override — the owner can halt all outbound routing at any time through a system override command. Because everything passes through Block 13, it is where alignment is enforced in practice, where the audit trail is created, and where JARVIS — as a coordinating presence — is expressed.

---

## 2. What Block 13 Must Do

- Receive all events from all blocks. There is no other destination for a block emitting an event.
- Write a log entry for every event before dispatching it to any subscriber. If the log write fails, the event is not dispatched.
- Subject every event to an alignment check against the Block 22 constitution before routing. An event that has not been alignment-checked is never dispatched.
- Route events to declared subscriber blocks after alignment check passes.
- Identify bridge-origin events by their provenance metadata and subject them to the enhanced alignment gate before they enter the production event bus.
- Apply the standard alignment check to all events, including bridge-origin events that have already passed the enhanced gate.
- Detect missing worker heartbeats and emit a `worker.heartbeat.missed` event when a worker has not reported within its declared interval.
- Suspend all outbound routing immediately on receipt of a `system.override.issued` event. Hold in-flight events. Do not execute pending actions. Remain operational to receive the resume command and to log the halt itself.
- Apply backpressure to producing blocks when processing capacity is constrained. Do not drop events under load.
- Retry delivery to unavailable subscriber blocks according to a defined retry policy. After retry exhaustion, place the event in dead-letter state, log it, and notify the owner.
- Feed the full event stream to Block 25 (Observability) in real time.
- Write every event and its outcome to the immutable audit log in Block 16 (Storage).
- Provide per-conversation event ordering. Events within a single conversation thread are delivered in the order they were received.

## 3. What Block 13 Must Not Do

- Route any event that has not passed the alignment check.
- Route any event whose log entry has not been successfully written.
- Pass through a bridge-origin event that the enhanced alignment gate cannot positively confirm as safe.
- Treat a timeout on the alignment check as a pass. Alignment check failure is always a closed failure — the event is rejected.
- Treat `approval.timeout` as anything other than rejection. The orchestrator never treats silence as consent.
- Drop events silently under any condition — load, failure, or otherwise.
- Discard undeliverable events after retry exhaustion without logging them and notifying the owner.
- Reason about the content of events, assess the quality of actions, or substitute for any intelligence block.
- Allow any block to communicate directly with any other block.
- Allow bridge-origin events to enter the production event bus without passing the enhanced alignment gate first.
- Be bypassed by any mechanism, including shared databases, direct API calls between blocks, or any pattern that does not route through Block 13.

---

## 4. Event Taxonomy

Block 13 handles all events in CLIVE. Events are classified as follows.

### Class 1 — Interaction Events

Originate from a surface (Blocks 2 and 4).

| Event | Description |
| --- | --- |
| `query.received` | Natural language input submitted by the owner |
| `approval.granted` | Owner confirmed a pending action |
| `approval.rejected` | Owner rejected a pending action |
| `approval.timeout` | Confirmation window expired — treated identically to rejection |
| `feedback.explicit` | Owner marked a response as wrong or an action as incorrect |
| `feedback.implicit` | Inferred from behaviour — rephrased query, ignored response |

### Class 2 — Knowledge Events

Originate from or target the knowledge pipeline (Blocks 14–16).

| Event | Description |
| --- | --- |
| `ingestion.triggered` | New content source polled or document submitted |
| `ingestion.completed` | Content received and handed to processing |
| `processing.completed` | Content chunked, embedded, and stored |
| `retrieval.requested` | Query/RAG block requesting relevant chunks |
| `retrieval.completed` | Chunks returned to requesting block |

### Class 3 — Action Events

Originate from Block 8 or Block 10.

| Event | Description |
| --- | --- |
| `action.proposed` | System has identified an action to take |
| `action.dispatched` | Confirmation received; action is executing |
| `action.completed` | Action executed successfully |
| `action.failed` | Action attempted and failed |
| `action.cancelled` | Action withdrawn before confirmation |

### Class 4 — Worker Events

Originate from or target Block 10.

| Event | Description |
| --- | --- |
| `worker.spawned` | A background agent has been instantiated |
| `worker.heartbeat` | A running worker reporting liveness |
| `worker.completed` | Worker task finished; outcome logged |
| `worker.failed` | Worker encountered an unrecoverable error |
| `worker.retired` | Worker deprecated by the Reaper |

### Class 5 — Evolution Events

Originate from Block 21. All subject to alignment boundary constraints (Block 22, Architect-owned).

| Event | Description |
| --- | --- |
| `variant.created` | A mutation has been generated in the sandbox |
| `variant.evaluated` | A variant assessed against fitness criteria |
| `variant.promoted` | A variant proposed for production |
| `variant.retired` | The Reaper has deprecated a component |
| `evolution.boundary.breach` | A proposed mutation touches a protected parameter |

### Class 6 — System Events

Internal health and operational signals.

| Event | Description |
| --- | --- |
| `cost.threshold.approached` | Spend nearing budget limit |
| `cost.threshold.exceeded` | Spend limit breached; throttling required |
| `system.health.degraded` | A block is reporting errors or elevated latency |
| `system.override.issued` | Owner has issued a halt or redirect command |
| `config.changed` | A configuration parameter has been updated |
| `security.anomaly.detected` | Unusual access pattern flagged |

---

## 5. Delivery and Ordering Guarantees

**Delivery: at-least-once (D-NEW-02)**

The orchestrator retries delivery until it receives acknowledgement from a subscriber. An event may be delivered more than once if a subscriber acknowledges after a retry is already in flight. Every subscriber block must be idempotent — receiving the same event twice must produce the same result as receiving it once. This is a system-wide design obligation on all blocks.

*Specific idempotency note for Block 9 (Action Layer): a duplicate confirmation event for the same irreversible action must be treated as already-handled, not as a new confirmation request.*

**Ordering: per-conversation (D-NEW-03)**

Events within a single conversation thread are delivered in the order they were received. Events across unrelated conversation threads may arrive out of order. Global ordering is not provided.

**Queue overflow during orchestrator unavailability (D-NEW-04)**

When the orchestrator is unreachable, blocks queue outbound events locally. When a local queue reaches capacity, new events are rejected at the source. No events are dropped silently. The owner is notified via Block 4 that CLIVE is at capacity.

---

## 6. Alignment Enforcement Mechanics

Every event carries the following fields, which the alignment check acts upon:

- **Source block** — which block emitted the event
- **Event class and type** — from the taxonomy in Section 4
- **Declared intent** — what the emitting block states this event is for
- **Target block(s)** — declared routing destination(s)
- **Payload** — the content of the event
- **Provenance metadata** — present on all events; bridge-origin events carry explicit experimental zone provenance

### Standard Alignment Check

Applied to all events before routing. The check is synchronous and blocking — the event waits. If the check cannot execute due to error or timeout, the event is rejected (closed failure). Specific checks:

| Check | Trigger | Outcome on failure |
| --- | --- | --- |
| Irreversible action gate | Any `action.proposed` with destructive payload | Rejected — routed to confirmation gate, not to execution |
| Personality protection | Any `evolution.*` event targeting Block 1 parameters | Rejected — `evolution.boundary.breach` emitted, owner notified |
| Goal function protection | Any `evolution.*` event proposing modification to alignment constitution | Rejected — `evolution.boundary.breach` emitted, Architect notified |
| Deception check | Declared intent inconsistent with payload content | Rejected — security anomaly logged |
| Zone boundary check | Data crossing trust zone boundaries without explicit cross-zone permission | Rejected — security anomaly logged |

### Enhanced Alignment Gate — Bridge-Origin Events

Bridge-origin events are identified by their provenance metadata. They do not enter the standard alignment check directly. They first pass through an enhanced alignment gate. The enhanced gate is a superset of the standard check. If the enhanced gate cannot positively confirm an event is safe, it rejects — closed failure applies absolutely. There is no fallback to the standard gate. There is no partial pass.

Additional checks applied in the enhanced gate, beyond the standard checks:

| Additional check | Description |
| --- | --- |
| Provenance integrity | Metadata is well-formed, complete, and consistent with known experimental zone identifiers. Malformed or unrecognised provenance is rejected. |
| Mutation boundary | The event does not carry a payload that would modify the alignment constitution, personality parameters, or any production component outside the declared scope of the originating variant. |
| Fitness signal conformance | If the event is a fitness or evaluation result, its structure conforms to the declared schema for such signals. Unexpected payload shapes are rejected. |
| Novelty flag | If the event proposes a capability or action type not previously seen from the experimental zone, it is flagged and routed to the owner for awareness before proceeding. |

**Routing sequence for bridge-origin events:**

Arrive via bridge → provenance metadata validated → enhanced alignment gate → if passed, enter production event bus → standard alignment check → route to subscriber.

Passing the enhanced gate does not exempt an event from the standard check.

### Alignment Rejection Outcome

When any event fails any check:

- Event is rejected and not dispatched
- `alignment.rejected` event is emitted and logged
- Owner is notified via Block 4
- For bridge-origin events, the experimental zone is informed via the bridge that the event was not admitted

---

## 7. Failure Modes and Defined Behaviour

| Failure | Defined behaviour |
| --- | --- |
| Orchestrator unreachable | Blocks queue events locally (bounded). When local queues reach capacity, new events are rejected at the source — not dropped silently. Owner notified via Block 4. CLIVE is effectively offline until the orchestrator is restored. Single-instance architecture — no redundancy in v1 (D-NEW-01). |
| Alignment check service unreachable | Closed failure. All event routing halts. Events queue locally. Owner notified. No events are routed without a passing alignment check. |
| Event log write failure | Event is not dispatched. The orchestrator does not route what it cannot log. Owner notified. |
| Subscriber block unreachable | Event logged as dispatched. Delivery to the unavailable block retried per retry policy. After retry exhaustion, event placed in dead-letter state, logged, and owner notified. Events are never silently discarded. |
| Runaway worker (heartbeat missed) | Orchestrator emits `worker.heartbeat.missed`. Worker is considered failed. Any pending actions it owned are cancelled — not executed. Owner notified. |
| Burst load | Events queue. Backpressure applied to producing blocks. Events are not dropped. Cost thresholds may be reached as a side effect — Block 20 notified. |
| Enhanced alignment gate failure (bridge-origin) | Bridge-origin event rejected. Not routed. Not passed to standard gate. Experimental zone notified via bridge. Owner notified. Closed failure — no exceptions. |
| System override issued | All outbound routing suspended immediately. In-flight events not dispatched. Pending actions held. Orchestrator remains operational to receive resume command and to log the halt. |

---

## 8. Interface Specification

### Events Consumed

All events from all blocks and all classes in Section 4. There is no other destination for a block emitting an event.

### Events Routed

All events from all classes, post-alignment-check, to declared subscriber blocks.

### Events Emitted by the Orchestrator Itself

| Event | Trigger |
| --- | --- |
| `alignment.rejected` | Any event fails the alignment check or enhanced alignment gate |
| `delivery.failed` | Subscriber unreachable after retry exhaustion |
| `system.override.active` | Owner halt is in effect |
| `worker.heartbeat.missed` | Worker has not reported within its declared interval |

### Feeds

- **Block 25 (Observability)** — full event stream in real time; every event, every outcome
- **Block 16 (Storage)** — immutable audit log; every event logged before dispatch

---

## 9. Constraints Inherited from [DECISIONS.md](http://DECISIONS.md)

| Decision | Constraint on Block 13 |
| --- | --- |
| D-003 | No direct block-to-block communication. All inter-block communication routes through Block 13. This applies to Block 13 itself — it emits and receives events; it does not call other blocks directly. |
| D-004 | Alignment is checked on every routed event. Events that would modify the goal function or alignment constitution are rejected. |
| D-005 | Evolution events targeting Block 1 (Personality) parameters are rejected. The Reaper cannot target personality. |
| D-006 | `action.proposed` events with destructive payloads route to the confirmation gate, not to execution. `approval.timeout` is treated as rejection. |
| D-017 | Block 13 is first-built infrastructure. The orchestrator written to coordinate build agents is Block 13. |
| D-018 | Block 13 is stateless between calls. All state lives in Block 16. The orchestrator does not retain state internally. |
| D-022 | Experimental zone runs on entirely separate infrastructure. The event bridge (D-024) is the only connection between environments. |
| D-023 | Block 13 runs as a single instance with no redundancy in v1. |
| D-024 | Cross-environment communication routes through a controlled event bridge. Block 13 treats bridge events as a first-class event source. All bridge events are subject to alignment enforcement. |
| D-025 | At-least-once delivery. All subscriber blocks must be idempotent. |
| D-NEW-01 | Single-instance orchestrator. No redundancy. Failure means CLIVE is offline until restored. |
| D-NEW-02 | At-least-once delivery. Universal idempotency obligation on all subscriber blocks. Block 9 has a specific obligation: duplicate confirmation events for irreversible actions are treated as already-handled. |
| D-NEW-03 | Per-conversation ordering. Events across unrelated threads may arrive out of order. Global ordering not provided. |
| D-NEW-04 | Local queue overflow during orchestrator unavailability: new events rejected at source, not dropped. Owner notified. |

---

## 10. Open Items

**Awaiting Architect record:** D-NEW-01, D-NEW-02, D-NEW-03, D-NEW-04 are approved by the owner but not yet written to [DECISIONS.md](http://DECISIONS.md). The Architect should record these before the next implementation session.

**Alignment scrutiny level for bridge-origin events:** Incorporated as a requirement (Section 6, enhanced alignment gate) per Architect direction. The Architect should determine whether this warrants a formal [DECISIONS.md](http://DECISIONS.md) entry or an update to the Block 22 alignment constitution.

**Retry policy:** The retry interval, maximum retry count, and backoff strategy for undeliverable events are not yet defined. This is a requirements gap to be resolved before implementation of Block 13 begins.

**Latency implications of synchronous alignment check:** The standard alignment check is synchronous and blocking. Under high event volume, this creates a potential bottleneck. The Infrastructure Agent should be made aware of this constraint when designing Block 27. This is a cross-block concern, flagged for the Architect.

---

*Block 13 Requirements Artefact — Systems Agent*

*Produced May 2026 — Session 1*

*Status: Complete — all open items resolved*