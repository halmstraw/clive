-- v0.8 — Block 17 Tool Registry: tool_registry table.
-- D-137: Block 17 Tool Registry storage layer — one row per registered tool.
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS,
--             CREATE OR REPLACE FUNCTION, CREATE OR REPLACE TRIGGER.
-- Note: numbers 07 and 08 are taken by 07_v03_tables.sql / 08_v04_tables.sql;
--       this file correctly continues the sequence at 12.

-- Trigger function: auto-update updated_at on any row modification.
-- CREATE OR REPLACE is idempotent; safe to re-run.
CREATE OR REPLACE FUNCTION clive_state.set_tool_registry_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Tool registry table (clive_state schema).
-- One row per registered tool. PRIMARY KEY on tool_name enforces uniqueness.
-- permission_scope: TEXT[] array of permission tokens, e.g. ARRAY['read:web'].
-- health_status: constrained to 'healthy' | 'degraded' | 'unavailable'.
-- deprecated: when TRUE, deprecation_note SHOULD be populated (application-enforced).
-- registered_at: set once on insert; updated_at maintained by trigger below.
CREATE TABLE IF NOT EXISTS clive_state.tool_registry (
    tool_name         TEXT        PRIMARY KEY,
    display_name      TEXT        NOT NULL,
    version           TEXT        NOT NULL,              -- semver, e.g. "1.0.0"
    description       TEXT        NOT NULL,
    permission_scope  TEXT[]      NOT NULL,              -- e.g. ARRAY['read:web']
    health_status     TEXT        NOT NULL DEFAULT 'healthy'
                          CHECK (health_status IN ('healthy', 'degraded', 'unavailable')),
    enabled           BOOLEAN     NOT NULL DEFAULT TRUE,
    deprecated        BOOLEAN     NOT NULL DEFAULT FALSE,
    deprecation_note  TEXT,                              -- nullable; populate when deprecated = TRUE
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger: auto-update updated_at whenever a row is modified.
-- CREATE OR REPLACE TRIGGER is idempotent (PostgreSQL 14+; system runs PG 16).
CREATE OR REPLACE TRIGGER trg_tool_registry_updated_at
    BEFORE UPDATE ON clive_state.tool_registry
    FOR EACH ROW EXECUTE FUNCTION clive_state.set_tool_registry_updated_at();

-- Index for fast runtime lookups by enabled/deprecated status.
-- Block 9 queries this at dispatch time to find active, non-deprecated tools.
CREATE INDEX IF NOT EXISTS idx_tool_registry_enabled_deprecated
    ON clive_state.tool_registry (enabled, deprecated);

GRANT ALL ON clive_state.tool_registry TO clive_app;
