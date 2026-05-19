# D-161 — System document versions loaded via SQL init scripts (IaC)

| Field | Value |
|---|---|
| ID | D-161 |
| Title | System document versions loaded via SQL init scripts (IaC) |
| Status | Accepted |
| Date | 2026-05-19 |
| Blocks | Block 1 (Personality), Block 16 (Storage), Block 27 (IaC), Block 28 (CI/CD) |
| Recorded by | Architect |

## Context

After D-159 merged, the owner ran `/activate personality` and received
"No pending personality document found." Root cause: the v0.2 personality
document exists in `docs/spec/` but no row had been INSERTed into
`clive_state.system_documents`. There was no IaC mechanism for loading
new system document versions — it required a manual DB operation.

This violates the project principle that all persistent state comes from IaC.
Manual DB operations are not repeatable, not reviewed, and not reflected in
the repo.

## Decision

New system document versions are loaded via SQL init scripts in
`infrastructure/sql/init/`. Each script uses `INSERT ... ON CONFLICT DO NOTHING`
so it is idempotent and safe to re-run.

The `is_active` column is always set to `false` in the init script. Activation
remains a separate two-step owner action via Telegram per D-049
(`/activate personality` → `/confirm_activate <version_id>`). Init scripts
must never set `is_active = true`.

**Immediate action:** Add `infrastructure/sql/init/24_personality_v02.sql`
to load the v0.2 personality document (D-159 Fix 4) with `is_active = false`.

**Pattern going forward:** Any new system document version (personality or
alignment_rules) ships with a corresponding numbered init script in the same
directory. The script is reviewed in the same PR as the document change.

## Alternatives considered

**Manual DB operation (rejected):** Requires SSH + psql on every deployment
that introduces a new document version. Not repeatable, not in version control,
not testable by CI.

**Telegram command for document loading (deferred):** A `/load_document` command
would allow the owner to upload content directly from Telegram. Deferred —
adds surface complexity and a new attack surface. SQL init scripts are
sufficient for a single-owner system where deploys are infrequent.

## Consequences

- New document versions are loaded automatically on each deploy (idempotent).
- Owner can run `/activate personality` immediately after deployment without
  a manual DB step.
- CI SQL idempotency tests cover new init scripts automatically.
- All document version history is visible in git.
