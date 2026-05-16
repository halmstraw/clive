# D-132 — CLIVE v0.7 Block 9 acceptance criteria

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks:** Block 9, Block 13, Block 23, Block 28

## Acceptance criteria

1. "search for X" message triggers action.pending (not query.received); no
   confirmation gate bypass.

2. After /confirm_action, search results from Brave API are delivered to
   Telegram as a numbered list with title, snippet, and URL.

3. "remind me about X at Y" message triggers action.pending with the parsed
   time shown in the confirmation prompt.

4. After /confirm_action, a row is written to clive_state.scheduled_reminders
   with status = 'pending' and the correct fire_at timestamp.

5. The reminder polling loop fires the reminder message to Telegram at or
   within 30 seconds of fire_at, and marks the row status = 'fired'.
   Double-fire is prevented by atomic UPDATE...RETURNING.

6. /cancel_action on a pending reminder emits action.rejected; no DB row
   is written.

7. A non-action message (e.g. "what is the capital of France?") routes to
   Block 8 RAG without triggering any action confirmation prompt.
