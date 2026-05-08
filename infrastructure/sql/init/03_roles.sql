-- Idempotent role creation
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clive_app') THEN
    CREATE ROLE clive_app LOGIN PASSWORD 'PLACEHOLDER_REPLACED_BY_ANSIBLE';
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clive_audit_writer') THEN
    CREATE ROLE clive_audit_writer LOGIN PASSWORD 'PLACEHOLDER_REPLACED_BY_ANSIBLE';
  END IF;
END
$$;

-- clive_app: full access to search and state schemas
GRANT CONNECT ON DATABASE clive TO clive_app;
GRANT USAGE ON SCHEMA clive_search TO clive_app;
GRANT USAGE ON SCHEMA clive_state TO clive_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA clive_search TO clive_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA clive_state TO clive_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA clive_search GRANT ALL ON TABLES TO clive_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA clive_state GRANT ALL ON TABLES TO clive_app;

-- clive_audit_writer: INSERT only on audit schema — enforces D-067
GRANT CONNECT ON DATABASE clive TO clive_audit_writer;
GRANT USAGE ON SCHEMA clive_audit TO clive_audit_writer;
-- Table-level INSERT grant applied in 04_audit_table.sql after table creation
