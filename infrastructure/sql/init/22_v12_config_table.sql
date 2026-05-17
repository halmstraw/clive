-- v0.12 — Block 19 Config/Admin: runtime configuration key/value store.
-- D-149: owner-managed config values; env vars are bootstrap-only fallback.
-- Idempotent: CREATE TABLE IF NOT EXISTS, ON CONFLICT DO NOTHING.
-- Depends on: 02_schemas.sql (clive_state schema must exist).

CREATE TABLE IF NOT EXISTS clive_state.config (
    config_key   TEXT        PRIMARY KEY,
    config_value TEXT        NOT NULL,
    description  TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by   TEXT        NOT NULL DEFAULT 'system'
);

-- clive_app needs SELECT, INSERT, UPDATE — no DELETE (append-only audit principle).
-- clive_audit_writer only touches the audit table; no access here.
GRANT SELECT, INSERT, UPDATE ON clive_state.config TO clive_app;
