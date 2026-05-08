-- Append-only audit log table — D-067
-- clive_audit_writer role has INSERT only; no UPDATE or DELETE possible
CREATE TABLE IF NOT EXISTS clive_audit.event_log (
  id               uuid        NOT NULL DEFAULT uuid_generate_v4(),
  event_id         uuid        NOT NULL,
  event_type       text        NOT NULL,
  source_block     integer     NOT NULL,
  timestamp        timestamptz NOT NULL,
  payload_hash     text        NOT NULL,
  alignment_result text        NOT NULL CHECK (alignment_result IN ('pass', 'fail', 'enhanced_pass', 'enhanced_fail')),
  routing_outcome  text        NOT NULL,
  conversation_id  uuid,
  zone_scope       text        NOT NULL DEFAULT 'personal',
  PRIMARY KEY (id),
  UNIQUE (event_id)
);

-- Immutable constraint: no updates or deletes at application layer
-- Storage-layer enforcement via INSERT-only role (D-067)
REVOKE UPDATE, DELETE ON clive_audit.event_log FROM clive_app;

-- Grant INSERT to audit writer role
GRANT INSERT ON clive_audit.event_log TO clive_audit_writer;

-- Index for correlation and replay
-- idx_audit_event_id omitted: UNIQUE (event_id) constraint creates the index implicitly
CREATE INDEX IF NOT EXISTS idx_audit_conversation ON clive_audit.event_log (conversation_id) WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON clive_audit.event_log (timestamp);
