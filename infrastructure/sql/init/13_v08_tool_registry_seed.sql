-- v0.8 — Block 17 Tool Registry: seed data for the three existing Block 9 tools.
-- D-137: promotes hardcoded Block 9 tools to first-class registry entries so
--         Block 9 can resolve them by tool_name rather than hardcoded conditionals.
-- Idempotent: ON CONFLICT (tool_name) DO NOTHING — safe to re-run.
-- Depends on: 12_v08_tool_registry.sql (table must exist).

INSERT INTO clive_state.tool_registry
    (tool_name, display_name, version, description, permission_scope,
     health_status, enabled, deprecated)
VALUES
    (
        'web_search',
        'Web Search',
        '1.0.0', -- NOSONAR
        'Searches the web via DuckDuckGo and returns summarised results',
        ARRAY['read:web'],
        'healthy', -- NOSONAR
        TRUE,
        FALSE
    )
ON CONFLICT (tool_name) DO NOTHING;

INSERT INTO clive_state.tool_registry
    (tool_name, display_name, version, description, permission_scope,
     health_status, enabled, deprecated)
VALUES
    (
        'reminder',
        'Reminder',
        '1.0.0', -- NOSONAR
        'Sets time-based reminders that deliver via Telegram',
        ARRAY['write:reminders', 'write:telegram'],
        'healthy', -- NOSONAR
        TRUE,
        FALSE
    )
ON CONFLICT (tool_name) DO NOTHING;

INSERT INTO clive_state.tool_registry
    (tool_name, display_name, version, description, permission_scope,
     health_status, enabled, deprecated)
VALUES
    (
        'delete_document',
        'Document Deletion',
        '1.0.0', -- NOSONAR
        'Permanently removes a document from Block 16 storage',
        ARRAY['write:storage'],
        'healthy', -- NOSONAR
        TRUE,
        FALSE
    )
ON CONFLICT (tool_name) DO NOTHING;
