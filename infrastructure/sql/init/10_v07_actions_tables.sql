-- v0.7 — Block 9 Action Layer: scheduled_reminders table
-- Idempotent: safe to run multiple times (D-002, CLAUDE.md constraint)

CREATE TABLE IF NOT EXISTS clive_state.scheduled_reminders (
    reminder_id      uuid        NOT NULL DEFAULT uuid_generate_v4(),
    chat_id          bigint      NOT NULL,
    message          text        NOT NULL,
    fire_at          timestamptz NOT NULL,
    conversation_id  uuid,
    status           text        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'fired', 'cancelled')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (reminder_id)
);

CREATE INDEX IF NOT EXISTS idx_scheduled_reminders_fire_at
    ON clive_state.scheduled_reminders (fire_at)
    WHERE status = 'pending';

GRANT ALL ON clive_state.scheduled_reminders TO clive_app;
