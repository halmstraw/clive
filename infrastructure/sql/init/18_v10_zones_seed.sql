-- v0.10 — Zones seed data: 'personal' zone.
-- D-050: single zone 'personal' at v0.1; zone enforcement active from day one.
-- D-143: v0.10 scope — Blocks 6 and 7.
-- Idempotent: ON CONFLICT DO NOTHING — safe to re-run.
-- Depends on: 17_v10_users_zones.sql (clive_state.zones table must exist).
-- No user rows here — owner registration is handled by Block 23 at startup (D-144).

INSERT INTO clive_state.zones (zone_name, description)
VALUES ('personal', 'Default personal zone — all owner data')
ON CONFLICT DO NOTHING;
