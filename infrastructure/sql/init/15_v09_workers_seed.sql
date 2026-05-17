-- v0.9 — Block 10 Workers: seed data for daily_digest and knowledge_maintenance.
-- D-140: registers the two initial workers in tool_registry and workers tables.
-- Idempotent: ON CONFLICT DO NOTHING on both tables — safe to re-run.
-- Depends on: 12_v08_tool_registry.sql, 14_v09_workers_tables.sql.
-- NOTE: tool_registry rows are inserted before workers rows (FK dependency).

-- Register daily_digest as a first-class tool.
INSERT INTO clive_state.tool_registry
    (tool_name, display_name, version, description, permission_scope,
     health_status, enabled, deprecated)
VALUES
    (
        'daily_digest',
        'Daily Digest',
        '1.0.0', -- NOSONAR
        'Summarises recent queries, actions, cost, feedback, and system health; delivers via Telegram once daily',
        ARRAY['read:queries', 'read:actions', 'read:cost', 'read:feedback', 'write:telegram'],
        'healthy', -- NOSONAR
        TRUE,
        FALSE
    )
ON CONFLICT (tool_name) DO NOTHING;

-- Register knowledge_maintenance as a first-class tool.
INSERT INTO clive_state.tool_registry
    (tool_name, display_name, version, description, permission_scope,
     health_status, enabled, deprecated)
VALUES
    (
        'knowledge_maintenance',
        'Knowledge Maintenance',
        '1.0.0', -- NOSONAR
        'Identifies stale unaccessed chunks and flags for owner review via confirmation gate; no autonomous deletion',
        ARRAY['read:storage', 'write:confirmations'],
        'healthy', -- NOSONAR
        TRUE,
        FALSE
    )
ON CONFLICT (tool_name) DO NOTHING;

-- Schedule daily_digest worker — 08:00 UTC daily.
INSERT INTO clive_state.workers
    (worker_name, schedule_type, cron_expression, execution_scope)
VALUES
    (
        'daily_digest',
        'cron',
        '0 8 * * *',
        ARRAY['read:queries', 'read:actions', 'read:cost', 'read:feedback', 'write:telegram']
    )
ON CONFLICT (worker_name) DO NOTHING;

-- Schedule knowledge_maintenance worker — 09:00 UTC every Monday.
INSERT INTO clive_state.workers
    (worker_name, schedule_type, cron_expression, execution_scope)
VALUES
    (
        'knowledge_maintenance',
        'cron',
        '0 9 * * 1',
        ARRAY['read:storage', 'write:confirmations']
    )
ON CONFLICT (worker_name) DO NOTHING;
