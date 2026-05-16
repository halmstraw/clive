-- v0.7 tables: Block 11 full cross-session memory (D-128, D-129).
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- D-025: idempotency enforced via primary key UUIDs.
-- D-065: pgvector extension already installed (01_extensions.sql).

-- memory_entities: named facts, preferences, commitments extracted from conversation turns.
--   entity_type: person | date | preference | commitment | fact
--   key:         short snake_case identifier for the fact (e.g. "colleague_name")
--   value:       the extracted value as a string
--   source_turn_id: nullable FK to conversation_turns — set NULL on turn delete
--   embedding:   1536-dim vector for pgvector cosine similarity search (D-096)
CREATE TABLE IF NOT EXISTS clive_state.memory_entities (
    entity_id       uuid        NOT NULL DEFAULT uuid_generate_v4(),
    entity_type     text        NOT NULL
                        CHECK (entity_type IN ('person','date','preference','commitment','fact')),
    key             text        NOT NULL,
    value           text        NOT NULL,
    source_turn_id  uuid        REFERENCES clive_state.conversation_turns(turn_id)
                        ON DELETE SET NULL,
    embedding       vector(1536),
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id)
);

-- IVFFlat index for pgvector cosine similarity search over memory entities.
-- lists=10 appropriate for small-to-medium entity tables (<10k rows).
CREATE INDEX IF NOT EXISTS idx_memory_entities_embedding
    ON clive_state.memory_entities
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE INDEX IF NOT EXISTS idx_memory_entities_source_turn
    ON clive_state.memory_entities (source_turn_id)
    WHERE source_turn_id IS NOT NULL;

GRANT ALL ON clive_state.memory_entities TO clive_app;

-- conversation_summaries: compressed summaries produced by memory consolidation.
-- When a conversation exceeds CONSOLIDATION_TURN_THRESHOLD (100) turns or has
-- turns older than CONSOLIDATION_AGE_HOURS (48h), the qualifying raw turns are
-- compressed into one row here and then deleted from conversation_turns.
--   turn_range_start / turn_range_end: turn_number bounds covered by this summary
--   turn_count:  how many raw turns were consolidated into this row
--   embedding:   1536-dim vector — reserved for future semantic retrieval over summaries
CREATE TABLE IF NOT EXISTS clive_state.conversation_summaries (
    summary_id          uuid    NOT NULL DEFAULT uuid_generate_v4(),
    conversation_id     uuid    NOT NULL,
    summary_text        text    NOT NULL,
    turn_range_start    integer NOT NULL,
    turn_range_end      integer NOT NULL,
    turn_count          integer NOT NULL,
    embedding           vector(1536),
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (summary_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_summaries_conversation
    ON clive_state.conversation_summaries (conversation_id);

-- IVFFlat index for pgvector cosine similarity search over summaries.
-- lists=10 appropriate for small summary tables.
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_embedding
    ON clive_state.conversation_summaries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

GRANT ALL ON clive_state.conversation_summaries TO clive_app;
