-- D-159 Fix 3: Unique index on memory_entities (entity_type, key)
--
-- Enables the ON CONFLICT (entity_type, key) upsert in memory.store_entities.
-- Without this index, repeated facts insert duplicate rows.
--
-- Idempotent: CREATE UNIQUE INDEX IF NOT EXISTS is safe to re-run.
--
-- Note: existing duplicate rows (if any) are not cleaned up by this migration.
-- They are benign — top-5 cosine retrieval is unaffected when k rows exist,
-- and deduplication is enforced going forward.

CREATE UNIQUE INDEX IF NOT EXISTS memory_entities_type_key_idx
    ON clive_state.memory_entities (entity_type, key);
