-- v0.3 tables: Block 9 Action Layer (pending_actions) and Block 18 Feedback.
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- D-025: all operations are idempotent.
-- D-067: feedback events are also written to clive_audit.event_log by Block 13.

-- Block 9 — pending confirmation requests (D-006).
-- Records every action awaiting owner confirmation, with status lifecycle:
-- pending → confirmed | rejected | timed_out
CREATE TABLE IF NOT EXISTS clive_state.pending_actions (
    action_request_id   uuid        NOT NULL DEFAULT uuid_generate_v4(),
    action_type         text        NOT NULL,          -- e.g. 'document.delete'
    action_target       text        NOT NULL,          -- source_key for deletion
    action_description  text        NOT NULL,          -- human-readable, shown to owner
    conversation_id     uuid,
    chat_id             bigint      NOT NULL,           -- surface routing back to owner
    status              text        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'confirmed', 'rejected', 'timed_out')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,           -- timeout boundary
    resolved_at         timestamptz,
    PRIMARY KEY (action_request_id)
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_status
    ON clive_state.pending_actions (status)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pending_actions_expires
    ON clive_state.pending_actions (expires_at)
    WHERE status = 'pending';

GRANT ALL ON clive_state.pending_actions TO clive_app;

-- Block 18 — explicit feedback records (D-100, now active for v0.3).
-- One row per feedback submission. No Evolution Engine wiring at v0.3.
-- D-067: feedback events also written to audit log by Block 13.
CREATE TABLE IF NOT EXISTS clive_state.feedback (
    feedback_id          uuid        NOT NULL DEFAULT uuid_generate_v4(),
    retrieval_event_id   uuid        NOT NULL,           -- event_id of query.response being tagged
    conversation_id      uuid,
    owner_chat_id        bigint      NOT NULL,
    feedback_type        text        NOT NULL DEFAULT 'poor_quality'
                             CHECK (feedback_type IN ('poor_quality')),
    submitted_at         timestamptz NOT NULL DEFAULT now(),
    chunk_ids            jsonb       NOT NULL DEFAULT '[]',   -- chunk_ids returned in tagged retrieval
    PRIMARY KEY (feedback_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_retrieval
    ON clive_state.feedback (retrieval_event_id);

CREATE INDEX IF NOT EXISTS idx_feedback_conversation
    ON clive_state.feedback (conversation_id)
    WHERE conversation_id IS NOT NULL;

GRANT ALL ON clive_state.feedback TO clive_app;
