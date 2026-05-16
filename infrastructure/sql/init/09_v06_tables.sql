-- v0.6 tables: Block 20 LLM usage tracking (D-125).
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- D-025: idempotency enforced via primary key on uuid.

-- LLM call usage log — one row per LLM API call from Block 8.
-- Used for daily spend aggregation (spend cap gate) and Prometheus metrics.
CREATE TABLE IF NOT EXISTS clive_state.llm_usage (
    id                uuid            NOT NULL DEFAULT uuid_generate_v4(),
    model             text            NOT NULL,
    prompt_tokens     integer         NOT NULL DEFAULT 0,
    completion_tokens integer         NOT NULL DEFAULT 0,
    cost_usd          numeric(12, 8)  NOT NULL DEFAULT 0,
    created_at        timestamptz     NOT NULL DEFAULT now(),
    PRIMARY KEY (id)
);

-- Index on created_at for efficient daily spend sum query
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at
    ON clive_state.llm_usage (created_at);

GRANT ALL ON clive_state.llm_usage TO clive_app;
