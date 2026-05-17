-- v0.10 — Block 17 Tool Registry: add zone_permissions column.
-- D-143: v0.10 scope — Block 7 Trust Zones require zone-scoped tool access control.
-- D-050: all existing tools default to zone 'personal'.
-- Idempotent: ADD COLUMN IF NOT EXISTS; UPDATE is a safe backfill on rows that
--             predate this migration (setting to same value on re-run is harmless).
-- Depends on: 12_v08_tool_registry.sql (clive_state.tool_registry table must exist).
-- No grant changes needed — clive_state.tool_registry already grants ALL to clive_app.

-- Add zone_permissions column. PostgreSQL backfills existing rows with the DEFAULT
-- immediately, so no row will have a NULL value after this statement.
ALTER TABLE clive_state.tool_registry
    ADD COLUMN IF NOT EXISTS zone_permissions TEXT[] NOT NULL DEFAULT ARRAY['personal'];

-- Explicit backfill: sets zone_permissions on any row that somehow has NULL or
-- an empty array. Safe on re-run: rows already set to ARRAY['personal'] are unchanged.
UPDATE clive_state.tool_registry
    SET zone_permissions = ARRAY['personal']
    WHERE zone_permissions IS NULL OR zone_permissions = '{}';
