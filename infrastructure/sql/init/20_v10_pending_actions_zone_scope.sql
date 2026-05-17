-- v0.10 — Block 9 pending_actions: add zone_scope column.
-- D-143: v0.10 scope — zone-aware action dispatch.
-- D-050: all existing pending actions default to zone 'personal'.
-- Idempotent: ADD COLUMN IF NOT EXISTS; CREATE INDEX IF NOT EXISTS.
-- Depends on: 07_v03_tables.sql (clive_state.pending_actions table must exist).
-- No grant changes needed — clive_state.pending_actions already grants ALL to clive_app.

-- Add zone_scope column. PostgreSQL backfills existing rows with DEFAULT 'personal'.
ALTER TABLE clive_state.pending_actions
    ADD COLUMN IF NOT EXISTS zone_scope TEXT NOT NULL DEFAULT 'personal';

-- Partial index for zone-scoped pending action lookups.
-- Scoped to status = 'pending' rows only — keeps the index small and targeted.
-- Future use: zone-aware action resolution when multiple zones are supported.
CREATE INDEX IF NOT EXISTS idx_pending_actions_zone
    ON clive_state.pending_actions (zone_scope)
    WHERE status = 'pending'; -- NOSONAR
