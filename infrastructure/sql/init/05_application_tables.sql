-- Knowledge chunks (Block 16 search index)
CREATE TABLE IF NOT EXISTS clive_search.chunks (
    chunk_id         uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_id      uuid        NOT NULL,
    content          text        NOT NULL,
    embedding        vector(1536),  -- Adjust dimensions to match embedding model
    source_attribution text      NOT NULL,
    zone_of_origin   text        NOT NULL DEFAULT 'personal',
    position         integer     NOT NULL,
    metadata         jsonb       NOT NULL DEFAULT '{}',
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_zone ON clive_search.chunks (zone_of_origin);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON clive_search.chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON clive_search.chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- System documents (personality, alignment rules) — Block 16
CREATE TABLE IF NOT EXISTS clive_state.system_documents (
    id               uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_type    text        NOT NULL CHECK (document_type IN ('personality', 'alignment_rules')),
    version_id       uuid        NOT NULL DEFAULT uuid_generate_v4(),
    document_content text        NOT NULL,
    zone_scope       text        NOT NULL DEFAULT 'personal',
    is_active        boolean     NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    UNIQUE (document_type, version_id)
);

-- Enforce: exactly one active version per document type
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_docs_active
    ON clive_state.system_documents (document_type)
    WHERE is_active = true;

-- Orchestrator state (retry tracking, subscriber registry, dead-letter)
CREATE TABLE IF NOT EXISTS clive_state.orchestrator_state (
    key   text NOT NULL PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

GRANT ALL ON clive_search.chunks TO clive_app;
GRANT ALL ON clive_state.system_documents TO clive_app;
GRANT ALL ON clive_state.orchestrator_state TO clive_app;
