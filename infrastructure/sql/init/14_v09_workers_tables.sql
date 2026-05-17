-- v0.9 — Block 10 Workers: worker registry and run log tables.
-- D-140: Block 10 Workers storage layer — schedule registry and execution history.
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- Depends on: 12_v08_tool_registry.sql (clive_state.tool_registry must exist).

-- Worker registry — one row per registered worker.
-- schedule_type: constrained to 'cron' or 'event_trigger'.
-- cron_expression: populated when schedule_type = 'cron'; NULL otherwise.
-- trigger_event: populated when schedule_type = 'event_trigger'; NULL otherwise.
-- execution_scope: permission tokens governing what the worker may access.
-- FK to tool_registry enforces that every worker has a registered tool entry.
CREATE TABLE IF NOT EXISTS clive_state.workers (
    worker_name      TEXT        PRIMARY KEY
                                 REFERENCES clive_state.tool_registry(tool_name),
    schedule_type    TEXT        NOT NULL
                                 CHECK (schedule_type IN ('cron', 'event_trigger')),
    cron_expression  TEXT,
    trigger_event    TEXT,
    execution_scope  TEXT[]      NOT NULL,
    last_run_at      TIMESTAMPTZ,
    next_run_at      TIMESTAMPTZ
);

-- Worker run log — one row per execution attempt.
-- status: lifecycle of a single run; defaults to 'running' on insert.
-- outcome_summary: human-readable result populated when status = 'success'.
-- error_detail: exception or error message populated when status = 'error'.
CREATE TABLE IF NOT EXISTS clive_state.worker_runs (
    run_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name      TEXT        NOT NULL
                                 REFERENCES clive_state.workers(worker_name),
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    status           TEXT        NOT NULL DEFAULT 'running'
                                 CHECK (status IN ('running', 'success', 'error', 'skipped')),
    outcome_summary  TEXT,
    error_detail     TEXT
);

-- Index: fast lookup of workers by schedule type (cron vs event_trigger).
CREATE INDEX IF NOT EXISTS idx_workers_schedule_type
    ON clive_state.workers (schedule_type);

-- Index: run history per worker ordered by trigger time — supports pagination
--        and last-run queries.
CREATE INDEX IF NOT EXISTS idx_worker_runs_worker_name
    ON clive_state.worker_runs (worker_name, triggered_at);

-- Index: status-based scan for monitoring dashboards and retry logic.
CREATE INDEX IF NOT EXISTS idx_worker_runs_status
    ON clive_state.worker_runs (status, triggered_at);

GRANT ALL ON clive_state.workers TO clive_app;
GRANT ALL ON clive_state.worker_runs TO clive_app;
