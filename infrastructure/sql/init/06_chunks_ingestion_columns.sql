-- Add ingestion tracking columns to clive_search.chunks (D-099, D-025).
-- Idempotent: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.

ALTER TABLE clive_search.chunks
    ADD COLUMN IF NOT EXISTS source_key    text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS content_hash  text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS content_tsv   tsvector;

-- Unique index on content_hash enables ON CONFLICT (content_hash) DO NOTHING
-- for idempotent re-ingestion (D-025).  content_hash is always a SHA-256 hex
-- digest in new rows; the DEFAULT '' only applies to pre-migration rows which
-- will not exist in practice.
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_content_hash
    ON clive_search.chunks (content_hash);

-- GIN index for full-text search on the stored tsvector.
CREATE INDEX IF NOT EXISTS idx_chunks_tsv
    ON clive_search.chunks USING gin (content_tsv)
    WHERE content_tsv IS NOT NULL;
