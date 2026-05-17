-- v0.9 — Block 16 Storage: chunk retrieval tracking columns.
-- D-140: enables knowledge_maintenance worker to identify stale, unaccessed chunks.
-- Idempotent: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- Depends on: 05_application_tables.sql (clive_search.chunks must exist).
-- No grant changes required: clive_search.chunks already grants to clive_app.

-- Add retrieval tracking columns to existing chunks table.
-- retrieval_count:   incremented each time a chunk is returned in a query result;
--                    zero means never retrieved since ingestion.
-- last_retrieved_at: NULL = never retrieved; populated on first retrieval and
--                    updated on every subsequent retrieval.
ALTER TABLE clive_search.chunks
    ADD COLUMN IF NOT EXISTS retrieval_count   INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_retrieved_at TIMESTAMPTZ;

-- Partial index: fast scan for chunks with retrieval_count = 0.
-- Used by knowledge_maintenance worker to identify stale content for owner review.
-- Partial predicate keeps the index compact — it covers only unaccessed rows.
CREATE INDEX IF NOT EXISTS idx_chunks_unaccessed
    ON clive_search.chunks (created_at)
    WHERE retrieval_count = 0;
