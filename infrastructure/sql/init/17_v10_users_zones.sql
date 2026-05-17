-- v0.10 — Blocks 6 (Users) and 7 (Trust Zones): zones and users tables.
-- D-143: v0.10 scope — Blocks 6 and 7 delivered this sprint.
-- D-144: v0.10 acceptance criteria — users/zones storage layer prerequisite.
-- D-050: zone enforcement active from day one; all content carries zone 'personal'.
-- D-057: Telegram channel-as-authentication; telegram_chat_id is the user identity.
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.
-- No owner row seeded here — owner registration is handled by Block 23 at startup (D-144).

-- clive_state.zones: one row per named trust zone.
-- zone_name is the canonical identifier referenced by clive_state.users.zone_access,
-- clive_search.chunks.zone_of_origin, and clive_state.tool_registry.zone_permissions.
-- 'personal' zone is seeded in 18_v10_zones_seed.sql.
CREATE TABLE IF NOT EXISTS clive_state.zones (
    zone_name    TEXT        PRIMARY KEY,
    description  TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- clive_state.users: one row per authorised CLIVE user.
-- telegram_chat_id: unique Telegram chat identifier (BIGINT to accommodate large IDs).
-- role: 'owner' has full system access; 'viewer' is read-only within their zone_access.
-- zone_access: TEXT[] of zone_names this user may access; defaults to ['personal'].
--              Application layer enforces that all entries exist in clive_state.zones.
CREATE TABLE IF NOT EXISTS clive_state.users (
    user_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT      UNIQUE NOT NULL,
    role             TEXT        NOT NULL
                                     CHECK (role IN ('owner', 'viewer')),
    zone_access      TEXT[]      NOT NULL DEFAULT ARRAY['personal'],
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index: fast lookup of users by telegram_chat_id.
-- Block 23 queries this on every inbound message to authorise the sender.
CREATE INDEX IF NOT EXISTS idx_users_telegram_chat_id
    ON clive_state.users (telegram_chat_id);

-- Index: role-based lookups (e.g. find all owner rows during startup validation).
CREATE INDEX IF NOT EXISTS idx_users_role
    ON clive_state.users (role);

GRANT ALL ON clive_state.zones TO clive_app;
GRANT ALL ON clive_state.users TO clive_app;
