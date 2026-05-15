-- v0.4 tables: Block 11 conversation memory (D-115).
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- D-025: idempotency enforced via UNIQUE (event_id, role).

-- Block 11 — conversation turn storage.
-- One row per user message and per assistant response.
-- turn_number is auto-assigned as MAX(turn_number)+1 within the conversation.
-- Keyed on (event_id, role) for idempotent at-least-once delivery (D-025).
CREATE TABLE IF NOT EXISTS clive_state.conversation_turns (
    turn_id         uuid        NOT NULL DEFAULT uuid_generate_v4(),
    event_id        uuid        NOT NULL,           -- query.received or query.response event_id
    conversation_id uuid        NOT NULL,
    turn_number     integer     NOT NULL,
    role            text        NOT NULL
                        CHECK (role IN ('user', 'assistant')),
    content         text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id),
    UNIQUE (event_id, role)                         -- D-025: idempotency key
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_conversation
    ON clive_state.conversation_turns (conversation_id, turn_number);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_created
    ON clive_state.conversation_turns (created_at);

GRANT ALL ON clive_state.conversation_turns TO clive_app;
