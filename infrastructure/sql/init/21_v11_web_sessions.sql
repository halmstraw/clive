-- v0.11 — Block 5 (Sync/State): web dashboard session management
-- D-146: session tokens for dashboard authentication
-- D-147 AC-3: dashboard auth via session token stored in this table
--
-- Session tokens are 64-character hex strings (32 random bytes).
-- Sessions expire after 30 days. The dashboard cleans up expired sessions
-- at login time. clive_app has full access; no new roles required.
--
-- Design: owner logs in with DASHBOARD_SECRET; on success a session token
-- is inserted here, set as an HTTP-only cookie, and checked on all API calls.
-- The user_id FK references clive_state.users (owner row inserted by Block 23).
--
-- Idempotent: all statements use IF NOT EXISTS or ON CONFLICT patterns.

CREATE TABLE IF NOT EXISTS clive_state.web_sessions (
    session_token  TEXT        PRIMARY KEY,
    user_id        UUID        NOT NULL
                               REFERENCES clive_state.users(user_id)
                               ON DELETE CASCADE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 days',
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for efficient expiry cleanup and token lookup
CREATE INDEX IF NOT EXISTS idx_web_sessions_expires_at
    ON clive_state.web_sessions (expires_at);

CREATE INDEX IF NOT EXISTS idx_web_sessions_user_id
    ON clive_state.web_sessions (user_id);

-- clive_app owns all dashboard session operations
GRANT ALL ON clive_state.web_sessions TO clive_app;
