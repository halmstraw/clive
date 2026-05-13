*Knowledge Agent requirements artefact — produced May 2026. Approved — Architect review complete May 2026.*

---
# Block 16 — Storage: v0.1 Requirements

**Produced by:** Knowledge Agent
**Date:** May 2026
**Scope:** v0.1 only (D-035)
**Status:** Approved — Architect review complete May 2026

---

## Governing Decisions

The following active decisions directly constrain this artefact:

- **D-002** — No technology choices in requirements
- **D-003** — Event bus principle; all inter-block communication via Block 13
- **D-025** — At-least-once delivery; all blocks must be idempotent
- **D-026** — Per-conversation event ordering only
- **D-027** — Point-in-time recovery; max data loss window declared before implementation
- **D-035** — v0.1 is query-only, single-surface; curated knowledge base
- **D-039** — Personality encoded as versioned constitutional document
- **D-043** — Retrieval is orchestrator-mediated synchronous call
- **D-046** — Block 8 idempotency via cached response (conversation-scoped) — Block 16 must support this pattern
- **D-047** — Confidence signal is retrieval quality metrics only
- **D-048** — Personality document stored in Block 16 as first-class retrievable item with version metadata

---

## v0.1 Scope Boundary

Block 16 at v0.1 is the persistent knowledge layer for a single-surface, query-only system. It stores curated knowledge (manually loaded, not continuously ingested), system documents (personality, alignment rules), and the immutable audit log. It serves retrieval requests brokered by Block 13 on behalf of Block 8.

Block 16 stores and retrieves. It does not reason, transform, or act. At v0.1, knowledge is curated — there is no continuous ingestion pipeline. Block 14 (Ingestion) and Block 15 (Processing) exist only in minimal manual-load form: a pathway to chunk, embed, and store documents that the owner provides directly. Block 16 defines what it needs from that pathway, not the pathway's full capability.

---

## Sub-Stores at v0.1

The specification defines five logical sub-stores. At v0.1, their scope is as follows:

### 1. Search Index

**Status: Active — primary v0.1 function.**

The search index is how Block 8 finds relevant knowledge. It supports hybrid retrieval: keyword matching, vector similarity, and semantic reranking. The index contains chunked, embedded documents from the curated knowledge base plus system documents (personality, alignment rules).

### 2. Raw Store

**Status: Active — minimal.**

Preserves original documents as loaded by the owner. Every document in the search index has a corresponding raw original. The raw store exists so that documents can be reprocessed if chunking or embedding strategies change post-v0.1. At v0.1 it is write-on-ingest and read-on-demand — not queried during normal retrieval.

### 3. Audit Log

**Status: Active — write-only at v0.1.**

Block 13 writes every event and its outcome to the audit log before dispatching. The audit log is append-only and immutable — no updates, no deletes, no truncation. At v0.1, the audit log is written to but not queried by any block other than Block 25 (Observability). Query capability over the audit log is a post-v0.1 concern.

### 4. State Store

**Status: Active — minimal.**

Block 13 is stateless between calls (D-018). Its operational state — subscriber registrations, retry state for in-flight events, dead-letter records — lives in Block 16's state store. At v0.1 the state store is small and low-throughput: one orchestrator instance (D-023), no workers, no evolution engine.

### 5. Memory Store

**Status: Empty at v0.1.**

Block 8 maintains per-conversation episodic memory in its own process memory during the conversation (D-046 response cache). Cross-conversation memory consolidation is post-v0.1. The memory store exists as a declared interface but holds no data at v0.1.

---

## What Block 16 Must Do

### 1. Serve retrieval requests from Block 13 on behalf of Block 8

This is Block 16's primary v0.1 function. Block 13 brokers a synchronous retrieval call (D-043) on Block 8's behalf. Block 16 receives the call, executes retrieval, and returns results to Block 13, which passes them to Block 8.

**Retrieval request contract (inbound from Block 13):**

| Field | Description |
|---|---|
| `retrieval_query` | Text query from the user's input (or Block 8's reformulated query) |
| `zone_scope` | One or more zone identifiers the requesting user is permitted to access |
| `result_limit` | Maximum number of chunks to return |
| `conversation_id` | For logging and correlation |

**Retrieval result contract (outbound to Block 13):**

| Field | Description |
|---|---|
| `ranked_chunks` | Ordered list of matching chunks, highest relevance first |
| `ranked_chunks[].content` | The text content of the chunk |
| `ranked_chunks[].source_attribution` | Identifier of the original document this chunk was extracted from |
| `ranked_chunks[].relevance_score` | Numeric score indicating match quality (normalised, comparable across queries) |
| `ranked_chunks[].zone_of_origin` | Which trust zone this chunk belongs to |
| `ranked_chunks[].chunk_id` | Stable identifier for this chunk |
| `result_count` | Total number of chunks returned |

**Behavioural requirements for retrieval:**

- Results are ranked by relevance, highest first.
- Zone boundaries are enforced at retrieval time. Block 16 never returns chunks from a zone not listed in `zone_scope`. This is a hard boundary, not a filter applied after retrieval.
- When no relevant results exist, Block 16 returns an empty result set with `result_count: 0`. This is not an error. Block 8 uses this as a low-confidence signal (D-047).
- Retrieval is idempotent within a reasonable window — the same request returns consistent results unless the underlying knowledge has changed. "Reasonable window" means within a single query lifecycle; Block 16 does not guarantee cross-query consistency if documents are being loaded concurrently.
- Block 16 does not interpret the query. It matches, scores, and returns. Reasoning is Block 8's job.

### 2. Store and retrieve system documents with version metadata

Two system documents are first-class stored items at v0.1:

**a) Personality document (Block 1, per D-048)**

- Stored as a retrievable item in Block 16 with version metadata.
- Version metadata includes: version ID, timestamp of creation, and a flag indicating whether this is the active version.
- Only one version is active at any time. Historical versions are retained for audit but not served in retrieval unless explicitly requested by version ID.
- Block 8 retrieves the personality document via the same orchestrator-mediated retrieval pattern (D-043) used for knowledge retrieval — but using a document-type identifier rather than a search query. The personality document is retrieved by identity, not by relevance matching.
- The personality document must be loadable into LLM context without transformation (Block 8 requirement).

**b) Alignment rules document (Block 22)**

- Same storage and versioning requirements as the personality document.
- Retrieved by identity, not by relevance matching.
- Active version served unless a specific version is requested.

**System document retrieval contract:**

| Field | Description |
|---|---|
| Request: `document_type` | Identifier: `personality` or `alignment_rules` |
| Request: `version_id` (optional) | If omitted, return active version |
| Request: `zone_scope` | Must include the zone where system documents reside |
| Response: `document_content` | The full document text |
| Response: `version_id` | The version identifier of the returned document |
| Response: `version_timestamp` | When this version was created |
| Response: `is_active` | Whether this is the currently active version |

This is a separate retrieval pathway from the search-based retrieval in section 1. System documents are not chunked, not embedded, and not returned as ranked results — they are retrieved whole by identity.

### 3. Accept and persist curated knowledge documents

At v0.1, the owner manually loads documents into CLIVE's knowledge base. Block 16 accepts pre-processed documents from a minimal Block 15 (Processing) pathway: documents that have already been chunked and embedded.

**Document ingestion contract (from Block 15 via Block 13):**

| Field | Description |
|---|---|
| `document_id` | Unique identifier for the source document |
| `raw_content` | Original document content (stored in raw store) |
| `chunks` | Array of processed chunks |
| `chunks[].chunk_id` | Unique identifier for this chunk |
| `chunks[].content` | Text content of the chunk |
| `chunks[].embedding` | Vector representation of the chunk |
| `chunks[].position` | Ordinal position within the source document |
| `chunks[].metadata` | Source document ID, zone assignment, processing timestamp |
| `zone_assignment` | Which trust zone this document belongs to |
| `document_metadata` | Title, source type, ingestion timestamp, owner-provided tags |

**Behavioural requirements for ingestion:**

- Ingestion is idempotent. Submitting the same `document_id` twice with identical content produces no change. Submitting the same `document_id` with different content is treated as an update: old chunks are replaced, new chunks are indexed, and the raw store is updated. The previous version of the raw document is retained.
- Zone assignment is immutable once set. A document cannot be moved between zones without deletion and re-ingestion. This prevents accidental zone boundary violations.
- Every ingested document has a corresponding raw store entry created atomically — if the raw store write fails, the chunks are not indexed.
- Block 16 emits a `processing.completed` event (via Block 13) after successful ingestion, confirming the document is retrievable.

### 4. Accept and persist audit log entries

Block 13 writes to the audit log before dispatching any event. The audit log is Block 16's most critical data integrity obligation.

**Audit log write contract (from Block 13):**

| Field | Description |
|---|---|
| `event_id` | Unique identifier for the event being logged |
| `event_type` | From Block 13's event taxonomy |
| `source_block` | Which block emitted the event |
| `timestamp` | When the event was received by Block 13 |
| `payload_hash` | Hash of the event payload (the payload itself may be stored or referenced) |
| `alignment_check_result` | Pass/fail/enhanced gate result |
| `routing_outcome` | Where the event was dispatched, or why it was rejected |
| `conversation_id` | If applicable |

**Behavioural requirements:**

- The audit log is append-only. No updates. No deletes. No truncation at v0.1.
- Audit log writes must be durable — a confirmed write survives process restart.
- Audit log writes must be fast enough not to become the bottleneck for Block 13's event routing. Block 13 does not dispatch until the log write confirms.
- Duplicate audit entries (same `event_id`) are accepted idempotently — the duplicate is acknowledged without creating a second entry.
- The audit log is partitioned by zone if the event carries zone context. Events without zone context (system events) are stored in a system partition.

### 5. Persist orchestrator state

Block 13 stores its operational state in Block 16 (D-018). At v0.1 this is minimal:

- Subscriber registry: which blocks subscribe to which event types.
- Retry state: events currently being retried, attempt count, next retry time.
- Dead-letter records: events that exhausted retries.

State reads and writes are keyed by state type and entity ID. They are idempotent — writing the same state value twice produces no change.

### 6. Support point-in-time recovery (D-027)

Block 16 must be recoverable to a recent known-good state. The maximum acceptable data loss window is bounded and must be declared by the owner before implementation begins. The specific value is an infrastructure cost trade-off — the Infrastructure Agent (Block 27) must propose concrete options with cost implications for the owner to decide against.

**Recovery requirements:**

- The maximum data loss window is bounded — unbounded data loss is unacceptable (D-027). The specific window value is not set by this requirements document. It is an input the Infrastructure Agent must resolve with concrete cost trade-offs before Block 16 implementation begins.
- The search index, raw store, and audit log must all be recoverable to the same point in time. Recovering the search index to a different point than the audit log is not acceptable — they must be consistent.
- Recovery does not require sub-second precision. Minute-level granularity is sufficient at v0.1.
- The recovery mechanism must be testable — the owner or infrastructure must be able to verify that recovery works before it is needed in production.
- Infrastructure for backup is provisioned via Block 27 (IaC).

---

## What Block 16 Must Not Do

1. **Reason about content.** Block 16 stores, indexes, and retrieves. It does not interpret queries, assess answer quality, or make judgments about relevance beyond scoring. Reasoning is Block 8's responsibility.
2. **Bypass the event bus.** All communication with other blocks routes through Block 13 (D-003). The orchestrator-mediated retrieval call (D-043) is Block 13 brokering a call — Block 16 does not communicate with Block 8 directly.
3. **Return cross-zone results.** Block 16 never returns knowledge from a zone not included in the `zone_scope` of the request. Zone enforcement is a retrieval-time hard constraint, not a post-retrieval filter.
4. **Modify the audit log.** The audit log is append-only and immutable. Block 16 does not provide update or delete operations on audit entries. No block may request such operations.
5. **Make technology assumptions.** No specific database, search engine, embedding model, or cloud platform is named in these requirements (D-002).
6. **Transform documents.** Block 16 stores pre-processed chunks. Chunking, embedding, and enrichment are Block 15's responsibility. Block 16 accepts the output of processing; it does not perform processing.
7. **Serve retrieval without zone scope.** Every retrieval request must include `zone_scope`. Block 16 rejects retrieval requests that do not specify which zones the caller is permitted to access.
8. **Persist cross-conversation state for Block 8.** Block 8's episodic memory and response cache are conversation-scoped and held in Block 8's process memory. Block 16 does not store per-conversation caches at v0.1.

---

## Interface Requirements

### What Block 16 Needs from Block 13 (Orchestrator)

Block 16 interacts with Block 13 in three ways:

**a) Retrieval brokering (D-043)**

Block 13 brokers synchronous retrieval calls on Block 8's behalf. Block 16 needs Block 13 to pass the retrieval request and return the result within the same call lifecycle. Block 16 does not need to know it is serving Block 8 — it serves Block 13, which is acting on Block 8's behalf.

Block 16 needs Block 13 to always include `zone_scope` in brokered retrieval calls. Block 13 determines zone scope from the user identity on the originating `query.submitted` event and the zone permissions defined by Block 7.

**b) Audit log writes**

Block 13 writes to Block 16's audit log before dispatching events. Block 16 needs these writes to include all fields specified in the audit log contract (section 4 above). Block 16 confirms the write, and Block 13 does not dispatch until confirmation is received.

**c) State persistence**

Block 13 reads and writes its operational state to Block 16. Block 16 needs state operations to be keyed and idempotent.

**d) Event emission**

Block 16 emits events (e.g., `processing.completed`) via Block 13. Block 16 needs Block 13 to accept and route these events through the standard alignment check and event bus.

### What Block 16 Needs from Block 7 (Trust Zones)

At v0.1, CLIVE likely operates with a single trust zone (personal). However, Block 16's design must not assume a single zone (Block 8 requirement). Block 16 needs the following from Block 7's zone definitions, declared as an interface requirement for whenever Block 7 is designed:

**a) Zone registry** — A list of defined zones, each with a unique zone identifier. Block 16 uses zone identifiers to partition stored knowledge and enforce retrieval boundaries.

**b) Zone assignment at ingestion** — Every document ingested into Block 16 carries a zone assignment. Block 16 needs this to be a valid zone identifier from the zone registry.

**c) Zone membership for retrieval** — When Block 13 brokers a retrieval call, it includes `zone_scope` — the zone(s) the requesting user is permitted to access. Block 16 needs this to be derived from the user identity and zone permission model defined by Block 7. Block 16 does not determine zone permissions — it enforces the scope it is given.

**d) Zone-specific retention policies (post-v0.1)** — At v0.1, no retention policies are enforced — all knowledge is retained indefinitely. Block 16 declares that it will need zone-specific retention policies when Block 7 is fully designed. This is a future interface requirement, not a v0.1 build item.

**Minimum v0.1 zone model (approved):**

Block 16 uses a single hard-coded zone identifier (`personal`) at v0.1. All documents and system documents are assigned to this zone. Block 13 passes this zone in every retrieval call. The zone enforcement mechanism is active — it enforces against one zone so the interface is proven before multiple zones exist. When the Access & Security Agent designs Block 7, the hard-coded identifier is replaced by the zone registry.

---

## System Document Storage — Detailed Requirements

D-048 establishes that Block 1 (Personality) is a document stored in Block 16, not a runtime service. The Block 22 alignment rules document has the same storage requirements. These are collectively "system documents."

### Version Lifecycle

1. A new version of a system document is created by writing it to Block 16 with a new version ID and `is_active: false`.
2. Activating a version is a separate operation: the new version is marked `is_active: true`, and the previously active version is marked `is_active: false`. This is atomic — there is never a moment with zero or two active versions of the same document type.
3. Previous versions are retained indefinitely at v0.1. They are queryable by version ID but are not served by default.
4. Activating a system document version requires explicit owner confirmation. At v0.1, this is a two-step process implemented in the configuration pathway: (a) submit the new document version (stored as `is_active: false`), (b) owner explicitly confirms activation (version marked `is_active: true`, previous active version marked `is_active: false`). Block 9 is not operational at v0.1, so the confirmation is handled by the configuration pathway directly. Post-v0.1, when Block 9 activates, system document activation routes through the Block 9 confirmation gate. **Pending DECISIONS.md entry.**

### Retrieval Distinction

System documents and knowledge chunks are retrieved through different mechanisms:

- **Knowledge retrieval:** Search-based. Query text matched against indexed chunks. Returns ranked results with relevance scores.
- **System document retrieval:** Identity-based. Document type identifier (`personality`, `alignment_rules`) plus optional version ID. Returns the complete document, unranked, unchunked.

Both mechanisms are brokered by Block 13 via the D-043 pattern. Block 13 distinguishes between the two by the shape of the retrieval request — a system document request carries `document_type`, a knowledge retrieval request carries `retrieval_query`.

---

## Idempotency (D-025)

Block 16 must handle duplicate operations gracefully:

- **Duplicate retrieval requests:** Return the same results. Retrieval is naturally idempotent (read operation).
- **Duplicate ingestion of the same document:** No change if content is identical. Treated as update if content differs.
- **Duplicate audit log writes (same event_id):** Acknowledged without creating a second entry.
- **Duplicate state writes:** Last-write-wins, but writing the same value twice produces no observable change.
- **Duplicate system document version creation (same version_id):** Acknowledged without creating a second version.

---

## Data Integrity Invariants

These invariants must hold at all times. Violation of any invariant is a system error.

1. **Every indexed chunk has a corresponding raw document.** If the raw store entry does not exist, the chunk must not be retrievable.
2. **Every retrieval result respects zone boundaries.** A chunk from zone A is never returned in a request scoped to zone B only.
3. **The audit log is append-only.** No mechanism exists to update or delete an audit entry.
4. **System documents always have exactly one active version per type.** Zero active versions or two active versions of the same type is a corruption state.
5. **Point-in-time recovery restores all sub-stores to the same point.** Inconsistency between the search index and the audit log after recovery is a corruption state.

---

## Dependencies and Flags for Architect

1. **Cross-block coordination with Intelligence Agent (Block 8).** The retrieval contract defined here matches Block 8's published requirements. Confirmed compatible: Block 8 requests `retrieval_query`, `zone_scope`, `result_limit`, `conversation_id` — Block 16 accepts all four. Block 16 returns `ranked_chunks` with `content`, `source_attribution`, `relevance_score`, `zone_of_origin` — Block 8 consumes all four. Block 16 additionally returns `chunk_id` (for traceability) and `result_count` (for D-047 confidence metrics). These are additive and do not conflict with Block 8's contract.
2. **System document retrieval pathway.** Block 8's requirements specify a retrieval interface for the personality document: "given the current personality version ID, return the personality document." The design here satisfies this via the system document retrieval contract (by `document_type`, optionally by `version_id`). Block 8 also needs "a version identifier so Block 8 can detect personality changes mid-session." Block 16 provides `version_id` in every system document retrieval response. **The Architect should confirm that this satisfies Block 8's interface requirement.**
3. **System document version activation — RESOLVED.** Owner decision: activation requires explicit owner confirmation. At v0.1, this is a two-step configuration pathway (submit, then confirm). Post-v0.1, activation routes through Block 9's confirmation gate. **The Architect should record this as a DECISIONS.md entry.**
4. **D-027 maximum data loss window — deferred to Infrastructure Agent.** The requirement is declared as bounded (unbounded data loss is unacceptable) and owner-declared before implementation begins. **The Infrastructure Agent must propose concrete options with cost trade-offs for the owner to decide against.** This is a blocking input for Block 16 implementation.
5. **Minimum v0.1 zone model — APPROVED.** Block 16 uses a single hard-coded zone identifier (`personal`) at v0.1. All documents and system documents are assigned to this zone. Block 13 passes this zone in every retrieval call. Zone enforcement is active from day one — the mechanism is exercised against one zone so it is proven before multiple zones exist. When the Access & Security Agent designs Block 7, the hard-coded identifier is replaced by the zone registry. **The Architect should record this as a DECISIONS.md entry.**
6. **Audit log as Block 13's critical dependency.** Block 13 does not dispatch events until the audit log write confirms. This makes Block 16's audit log write performance a system-wide latency constraint. **The Infrastructure Agent should be aware of this when designing Block 27.**

---

*Knowledge Agent — Block 16 v0.1 Requirements*
*May 2026*
