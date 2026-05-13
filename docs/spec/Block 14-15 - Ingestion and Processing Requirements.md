*Knowledge Agent requirements artefact — produced May 2026. Approved. Primary input for Claude Code implementation of the ingestion pipeline. Read alongside the Block 16 requirements artefact and DECISIONS.md.*

---
# Blocks 14 & 15 — Ingestion & Processing: v0.1 Requirements

**Status:** Approved | May 2026 | Knowledge Agent

---

## Prerequisites

Two prerequisites must be satisfied before any Block 14 or Block 15 implementation begins.

### P-1 — Schema migration `06_chunks_ingestion_columns.sql`

Three columns are absent from `clive_search.chunks` and must be added before Block 15 can write to it.

```sql
-- Migration: 06_chunks_ingestion_columns.sql
-- Adds columns required for Block 15 ingestion writes.
-- Apply before Block 15 or Block 14 implementation begins.

ALTER TABLE clive_search.chunks
    ADD COLUMN source_key    text        NOT NULL,
    ADD COLUMN content_hash  text        NOT NULL,
    ADD COLUMN content_tsv   tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

-- GIN index for full-text search (D-065)
CREATE INDEX chunks_content_tsv_idx
    ON clive_search.chunks
    USING GIN (content_tsv);

-- Partial unique index for deduplication (D-025)
CREATE UNIQUE INDEX chunks_dedup_idx
    ON clive_search.chunks (content_hash, zone_id, source_key);
```

**Column definitions:**

- `source_key text NOT NULL` — the MinIO object key for the raw document this chunk came from (D-068). The existing `document_id uuid` column is retained; `source_key` is the direct blob reference Block 15 needs without a join.
- `content_hash text NOT NULL` — SHA-256 hex of the chunk's UTF-8 text. Used for idempotent deduplication on re-ingestion (D-025). Enforced at the database layer via `chunks_dedup_idx`.
- `content_tsv tsvector GENERATED ALWAYS AS (...) STORED` — pre-computed tsvector for full-text search. Generated on write, indexed via GIN. Required for the keyword half of hybrid retrieval (D-065). English dictionary at v0.1; multilingual is deferred.
- `chunks_dedup_idx` — unique index on `(content_hash, zone_id, source_key)`. Enforces idempotency at the storage layer. `INSERT ... ON CONFLICT DO NOTHING` is the application-side pattern.

### P-2 — MinIO `clive-raw` bucket

The `clive-raw` bucket must exist in MinIO before any ingestion run. This is a known bootstrap gap (D-094). Block 14 fails clearly — not silently — if the bucket is absent: `ingest.failed` with reason `raw_store_bucket_missing`.

**Block 29 runbook entry required:** "Create `clive-raw` bucket in MinIO before first ingestion run."

---

## Block 15 — Processing Pipeline

### What Block 15 must do

Block 15 receives a raw document (bytes plus metadata) that has been stored in the MinIO raw store. It produces chunked, embedded knowledge records written to `clive_search.chunks` in Block 16. It does not communicate with Block 16 directly — it emits events; Block 13 brokers all reads and writes (D-003, D-043).

### Inputs

Block 15 receives a `document.stored` event from Block 13. Payload:

- `document_id` — uuid, identifier for this ingestion job
- `source_key` — MinIO object key where raw bytes are stored
- `zone_id` — "personal" at v0.1 (D-050)
- `media_type` — declared content type (`application/pdf`, `text/plain`, `text/markdown`)
- `filename` — original filename as submitted
- `event_id` — uuid, for idempotency cache keyed to this processing run (D-025, D-046)

### Processing steps

**Step 1 — Fetch raw document**

Block 15 retrieves raw bytes from MinIO using `source_key`. If the object does not exist, emit `processing.failed` with reason `source_not_found` and halt. No retry — absent source is not a transient failure.

**Step 2 — Text extraction**

Extract plain text from raw bytes according to `media_type`:

- `text/plain`, `text/markdown` — read as UTF-8 directly
- `application/pdf` — extract text layer; if text layer is absent (scanned PDF), emit `processing.failed` with reason `unsupported_format` and halt. OCR is deferred.
- Any other media type — emit `processing.failed` with reason `unsupported_format` and halt.

Normalise extracted text: strip leading/trailing whitespace, collapse multiple blank lines to one.

**Step 3 — Chunking**

Fixed-size chunking with overlap at v0.1 (D-097):

- **Chunk size:** 512 tokens, measured by the tokeniser of the configured embedding model
- **Overlap:** 50 tokens between adjacent chunks
- **Minimum chunk size:** 50 tokens — chunks below this threshold are merged with the preceding chunk, not emitted as standalone records
- Chunks are assigned a zero-based sequence index within the document

**Step 4 — Deduplication check**

For each chunk, compute `content_hash` = SHA-256 of the chunk's UTF-8 text (hex-encoded). Block 15 emits a `chunk.dedup_check` sub-event to Block 13, which queries Block 16 for existence of `(content_hash, zone_id, source_key)`. If a match exists, the chunk is skipped — no embedding, no write.

**Step 5 — Embedding**

For each non-skipped chunk, request an embedding via LiteLLM. Configured model at v0.1: `openai/text-embedding-3-small`, dimension 1536 (D-096). Retry policy: up to 3 attempts, 1-second initial backoff, doubling on each attempt. If all retries exhausted, emit `processing.failed` with reason `embedding_unavailable` and halt. Partial completion is reported accurately — the document is not marked complete.

**Step 6 — Write to Block 16**

For each embedded chunk, emit a `chunk.ready` event to Block 13 carrying:

- `document_id`
- `source_key`
- `zone_id`
- `chunk_index`
- `content` — chunk text
- `content_hash` — SHA-256 hex
- `embedding` — float array, 1536 dimensions

Block 13 brokers the write to Block 16. Block 16 executes `INSERT ... ON CONFLICT (content_hash, zone_id, source_key) DO NOTHING` — idempotent at the database layer (D-025).

**Step 7 — Completion event**

On all chunks processed or skipped, emit `processing.completed` carrying:

- `document_id`
- `source_key`
- `zone_id`
- `chunks_total` — total chunks before dedup
- `chunks_written` — chunks actually written
- `chunks_skipped` — dedup skips
- `processing_duration_ms`

### What Block 15 must not do

- Must not call Block 16 directly — all reads and writes route through Block 13 (D-003)
- Must not delete or overwrite existing chunks — write is always insert-or-skip; deletion routes through Block 9 confirmation gate (D-006)
- Must not hardcode embedding provider — provider and model are configuration values (D-096, D-077)
- Must not accept a `zone_id` other than "personal" at v0.1

### Idempotency

Block 15 is idempotent (D-025). Given the same `document_id` and `source_key`, a repeated run produces the same result. Re-runs of already-processed documents result in all chunks skipped at Step 4. `processing.completed` is still emitted with accurate counts.

### Events emitted by Block 15

| Event | When |
|---|---|
| `processing.started` | On receipt of `document.stored`, before Step 1 |
| `chunk.dedup_check` | Per chunk, before embedding (orchestrator-mediated sub-event) |
| `chunk.ready` | Per non-skipped chunk, after embedding |
| `processing.completed` | On successful completion of all chunks |
| `processing.failed` | On any halting failure, with reason field |

### Integration test requirements (D-095)

CI integration tests must cover:

1. Insert a known plain-text document into a test MinIO bucket, trigger `document.stored`, assert expected chunk rows exist in `clive_search.chunks` with non-null embeddings
2. Re-run the same document, assert no new rows inserted (idempotency)
3. Assert `processing.completed` emitted with correct `chunks_written` and `chunks_skipped` counts
4. Trigger with a scanned PDF (no text layer), assert `processing.failed` with reason `unsupported_format`
5. Trigger with an oversized payload, assert correct failure handling

Test embeddings use a stub function returning a fixed zero-vector of 1536 dimensions — no OpenAI API calls in CI.

---

## Block 14 — Ingestion Entry Point

### What Block 14 must do

At v0.1, Block 14 accepts a document dropped by the owner via the Telegram `/ingest` command. It stores the raw document in the MinIO `clive-raw` bucket and emits `document.stored` to trigger Block 15. Block 14 does not process or chunk documents.

### Trigger

Owner sends a file to the CLIVE Telegram bot with `/ingest` as the caption on the file attachment. Implementation detail: if Telegram delivers the command and file as separate messages, Block 4 is responsible for correlating them before emitting `ingest.requested`. This is a Block 4 / Experience Agent concern, not a Block 14 concern.

### Inputs

Block 4 delivers an `ingest.requested` event to Block 13, which routes it to Block 14. Event payload:

- `event_id` — uuid, for idempotency
- `file_bytes` or `telegram_file_id` — raw bytes or Telegram server-side file reference
- `filename` — original filename
- `media_type` — as declared by Telegram, or inferred from extension if absent
- `file_size_bytes` — as reported by Telegram

### Processing steps

**Step 1 — Validate**

- File is non-empty
- `media_type` is in permitted set: `text/plain`, `text/markdown`, `application/pdf`
- `file_size_bytes` does not exceed 10 MB (D-098)

If any validation fails, emit `ingest.rejected` with a reason string. Block 13 routes to Block 4, which replies to the owner via Telegram.

**Step 2 — Generate storage key**

Generate `document_id` as a new uuid. Construct `source_key`:

```
personal/{document_id}/{filename}
```

**Step 3 — Write to raw store**

Write raw bytes to MinIO at `source_key`. Retry policy: up to 3 attempts, 1-second initial backoff, doubling. If all retries fail, emit `ingest.failed` with reason `raw_store_unavailable`. If bucket does not exist, emit `ingest.failed` with reason `raw_store_bucket_missing` — no retry.

The write is atomic with respect to the `document.stored` event: if the raw store write fails, no `document.stored` event is emitted.

**Step 4 — Emit document.stored**

On successful raw store write, emit `document.stored` carrying:

- `document_id`
- `source_key`
- `zone_id` = "personal"
- `media_type`
- `filename`
- `event_id` (new uuid, distinct from the `ingest.requested` event_id, for Block 15 idempotency)

**Step 5 — Acknowledge to owner**

Emit `ingest.acknowledged`. Block 13 routes to Block 4, which sends a Telegram reply: document accepted, processing underway. Owner is not held waiting for Block 15 to complete.

When `processing.completed` arrives (routed from Block 15 via Block 13 to Block 4), Block 4 sends a follow-up Telegram message to the owner: filename, chunks written, chunks skipped.

### What Block 14 must not do

- Must not call MinIO directly — raw store write is Block 13-mediated (D-003)
- Must not trigger Block 15 directly — `document.stored` is the trigger; Block 13 routes it
- Must not process or chunk the document
- Must not accept files outside the permitted media type list
- Must not accept files above 10 MB

### Idempotency

Block 14 is idempotent (D-025). On duplicate `ingest.requested` event (same `event_id`), Block 14 returns the prior `ingest.acknowledged` without re-writing to the raw store. Raw store writes use `document_id` as the key component — a duplicate write to the same key is a no-op on MinIO.

### Events emitted by Block 14

| Event | When |
|---|---|
| `ingest.acknowledged` | On successful raw store write |
| `ingest.rejected` | On validation failure |
| `ingest.failed` | On raw store write failure after retries, or bucket absent |

### Integration test requirements (D-095)

CI integration tests must cover:

1. Send `ingest.requested` with a small plain-text file, assert raw bytes appear in MinIO test bucket under the expected key, assert `document.stored` emitted with correct metadata, assert `ingest.acknowledged` emitted
2. Re-send the same `event_id`, assert no duplicate raw store write
3. Send a file above 10 MB, assert `ingest.rejected` with appropriate reason
4. Send an unsupported media type, assert `ingest.rejected`
5. Simulate MinIO unavailable, assert `ingest.failed` with reason `raw_store_unavailable`

---

## Decisions flagged for DECISIONS.md

The following are flagged for the Architect to record. Content is ready; the Architect writes the entries.

**FLAG-1 → D-097** — Chunking parameters at v0.1: fixed-size, 512-token chunks, 50-token overlap, 50-token minimum chunk size. Chunks below minimum are merged with the preceding chunk.

**FLAG-2 → D-098** — Maximum ingestion file size at v0.1: 10 MB. Owner confirmed. Files above this limit are rejected at Block 14 validation with reason included in `ingest.rejected` event.

**FLAG-3** — Block 14 Telegram command/file correlation (whether `/ingest` is a caption or a separate command) is a Block 4 / Experience Agent concern. Flagged for the Architect to route when the Experience Agent is activated.

---

## Blocks 17 and 18

Deferred. Not on the v0.1 critical path. No requirements work this session.

---

*Knowledge Agent | May 2026*
