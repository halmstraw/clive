-- v0.7 patch — add metadata column to pending_actions for arbitrary action payload.
-- Stores extra fields (e.g. reminder fire_at) that are not in named columns so
-- they survive through to action.confirmed. Idempotent.
ALTER TABLE clive_state.pending_actions
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}';
