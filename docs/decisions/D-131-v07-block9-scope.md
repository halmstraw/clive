# D-131 — CLIVE v0.7 Block 9 Action Layer scope approved

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks:** Block 9, Block 13, Block 23, Block 16, Block 27, Block 28

## Decision

Extend Block 9 (Action Layer) with two new action types delivered end-to-end
through the existing D-006 confirmation gate:

1. **Web search** — "search for X" intent detected in Block 23, routed via
   Block 13 action.pending → action.confirmed → orchestrator calls Brave Search
   API (or SerpAPI) and delivers formatted results to Telegram.

2. **Scheduled reminders** — "remind me about X at Y" intent parsed with
   python-dateutil and CLIVE_TIMEZONE, confirmation prompt shows parsed time,
   confirmed action stored in clive_state.scheduled_reminders, fired by a
   30-second polling loop using atomic UPDATE...RETURNING (D-025 idempotent).

## Constraints honoured

- D-006: both action types pass through the confirmation gate before execution
- D-003: Block 23 does not call search APIs directly — routes via Block 13 events
- D-025: reminder poll uses atomic UPDATE...RETURNING to prevent double-fire
- SEARCH_API_KEY stored in /etc/clive/secrets.env, never in code or repo

## IaC

- SQL migration: infrastructure/sql/init/10_v07_actions_tables.sql
- SQL migration: infrastructure/sql/init/11_v07_pending_actions_metadata.sql
- Deploy pipeline: SEARCH_API_KEY sourced from GitHub Actions secret
- docker-compose.yml: SEARCH_API_PROVIDER (orchestrator), CLIVE_TIMEZONE (telegram)
