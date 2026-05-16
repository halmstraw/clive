# D-133 — CLIVE v0.7 Block 9 signed off

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks:** Block 9, Block 13, Block 23, Block 16, Block 27, Block 28

## Sign-off

All seven acceptance criteria from D-132 met and verified by the owner via
live Telegram testing on 2026-05-16.

| Criterion | Result |
|---|---|
| 1. Search intent → action.pending | ✅ |
| 2. Confirmed search → results delivered | ✅ |
| 3. Reminder intent → confirmation with parsed time | ✅ |
| 4. Confirmed reminder → DB row written | ✅ |
| 5. Poll loop fires reminder within 30s | ✅ |
| 6. /cancel_action → no DB row written | ✅ |
| 7. Non-action message → RAG passthrough | ✅ |

## Bugs fixed during session

- SEARCH_API_KEY missing from deploy pipeline secrets writer (deploy.yml)
- Telegram Markdown stripped underscores from error message var names
- action.pending metadata not persisted — reminder fire_at lost at confirmation
  (fixed by metadata jsonb column, migration 11_v07_pending_actions_metadata.sql)
- SQL migration loops in Ansible roles stopped at v0.4 — v0.6 and v0.7 tables
  would never have been created on a fresh provision (now fixed)
- SQL file for actions tables placed in dead Ansible files/ path instead of
  infrastructure/sql/init/ (removed duplicate)
