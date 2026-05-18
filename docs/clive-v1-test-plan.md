# CLIVE v1.0 — System Test Plan

**Version:** 1.0  
**Date:** 2026-05-18  
**Status:** Active  
**Owner:** Tim Halmshaw  
**Decisions covered:** D-094 (v1 acceptance), D-154 (v1.0 sign-off)

---

## Purpose

This is the manual end-to-end test plan for CLIVE v1.0. It validates every
in-scope block against the acceptance criteria established through D-094 to
D-154. It is the definitive test reference before v1 is declared
production-stable and before any v2 scope is opened.

Run this plan on the live production stack (Hetzner VM). It is a human-driven
test: each test case requires a real person to perform steps and verify
outcomes. There are no automated assertions here — this is the acceptance
sign-off checklist.

Blocks 21 (Evolution Engine) and 26 (Physical Device) are formally gated and
are **not tested**. Blocks 30–38 (Business Layer) are out of v1 scope.

---

## Prerequisites

Before starting any test section, confirm the following:

- [ ] SSH access to the Hetzner VM is available
- [ ] The GitHub Actions runner on the VM is online (green in repo Settings → Runners)
- [ ] Telegram is open and you are signed in as the owner account
- [ ] You have the owner chat ID available (`TELEGRAM_OWNER_CHAT_ID` from `/etc/clive/secrets.env`)
- [ ] A browser is available for dashboard testing
- [ ] A small test document (e.g. a plain text `.txt` file, ~1 KB) is ready to ingest
- [ ] A second test document (for deletion testing) is ready

---

## Section 1 — Infrastructure Readiness

**Purpose:** Confirm all containers are healthy and the network stack is reachable.

### 1.1 — All containers healthy

On the VM, run:

```bash
cd /home/clive/compose && docker compose ps
```

**Expected:** Every in-scope container is in `running` state with health `healthy`.

Required healthy containers:
- `clive-orchestrator`
- `clive-processing`
- `clive-query`
- `clive-telegram`
- `clive-dashboard`
- `clive-postgres`
- `clive-minio`
- `clive-caddy`
- `clive-alloy`
- `clive-node-exporter`
- `clive-postgres-exporter`

**Not expected to be running (gated):**
- `clive-sandbox` — profiles: experimental only (D-152 AC-3)

**Not expected to be running (one-shot):**
- `clive-seed` — exits after seeding

---

### 1.2 — Service health endpoints reachable

From the VM, check each internal service health. Services do not expose ports to
the host — curl must run inside the container network via `docker exec`:

```bash
docker exec clive-orchestrator curl -sf http://localhost:8080/health
docker exec clive-query        curl -sf http://localhost:8081/health
docker exec clive-telegram     curl -sf http://localhost:8082/health
docker exec clive-processing   curl -sf http://localhost:8083/health
docker exec clive-dashboard    curl -sf http://localhost:8084/health
```

**Expected:** Each returns HTTP 200 with a JSON body containing `"status": "ok"`.

---

### 1.3 — Public HTTPS access

From a browser or from outside the VM:

```
https://clive.halmshaw.co.uk/health
```

**Expected:** HTTP 200, TLS certificate valid, no browser security warnings.
Body: `{"status": "ok", "block": 2, "surface": "dashboard"}`.

---

### 1.4 — PostgreSQL connectivity

```bash
docker exec clive-postgres pg_isready -U postgres -d clive
```

**Expected:** `/var/run/postgresql:5432 - accepting connections`

---

### 1.5 — MinIO connectivity

```bash
docker exec clive-minio curl -sf http://localhost:9000/minio/health/live
```

**Expected:** HTTP 200 or empty 200 response (MinIO health endpoint).

---

### 1.6 — Audit log append-only enforcement

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SET ROLE clive_audit_writer;
  UPDATE clive_audit.event_log SET source_block = 0 WHERE FALSE;
"
```

**Expected:** `ERROR: permission denied for table event_log` — UPDATE is not
permitted for `clive_audit_writer` (D-067).

---

## Section 2 — Telegram Surface — Core Commands

**Purpose:** Validate all Telegram commands work correctly as owner.

Before this section, confirm the Telegram bot is running by sending any
message. CLIVE should respond.

---

### 2.1 — Authentication gate (non-owner rejection)

Ask a second Telegram account (or create a fresh one) to send any message to
the CLIVE bot.

**Expected:** CLIVE returns no response. The non-owner message is silently
ignored (D-057). No error or acknowledgement is sent to the non-owner.

---

### 2.2 — /help

Send `/help` to the bot.

**Expected:** Response lists all available commands:
- /start, /list, /status, /whoami
- /ingest, /ingest_confirm, /delete
- /tools, /tool_disable, /tool_enable
- /bad, /activate, /help

---

### 2.3 — /start

Send `/start` to the bot.

**Expected:** Response is `"Ready."`. Conversation session is reset.
Sending `/start` again resets again with the same response.

---

### 2.4 — /whoami

Send `/whoami` to the bot.

**Expected:** Response shows:
- Chat ID matching `TELEGRAM_OWNER_CHAT_ID`
- Role: `owner`
- Zone access: `personal`
- Member since: a valid date

---

### 2.5 — /status (baseline)

Send `/status` to the bot.

**Expected:** Response contains:
- Knowledge base: `N document(s), M chunk(s)` (or "empty" if no docs yet)
- Last query: date or "none yet"
- LLM spend today: `$0.XXXX`
- Daily cap line (cap set or "no cap set")
- `/list — see all documents` footer

---

### 2.6 — /list (baseline)

Send `/list` to the bot.

**Expected:**
- If no documents ingested: message explains how to ingest (desktop and mobile flows)
- If documents exist: numbered list with filename, chunk count, and date

---

## Section 3 — Ingestion Pipeline (Blocks 14 / 15)

### 3.1 — Desktop ingest (caption flow)

On Telegram desktop:
1. Attach the small test document
2. Type `/ingest` in the caption field
3. Send

**Expected (immediate):** `"Received <filename>. Processing — I will follow up when done."`

**Expected (follow-up, ~10–30 seconds):** `"Done. <filename> ingested — N new chunk(s) stored."`

---

### 3.2 — Document visible in /list after ingest

Send `/list` after 3.1 completes.

**Expected:** The ingested document appears in the list with the correct filename,
a chunk count > 0, and today's date.

---

### 3.3 — Mobile ingest (document-received flow)

On Telegram mobile (or simulate by sending a file without a caption):
1. Send the document without any caption or command

**Expected:** CLIVE responds with:
`"Ingest <filename>? Send /ingest_confirm to proceed, or ignore to cancel."`

2. Send `/ingest_confirm`

**Expected (immediate):** `"Received <filename>. Processing — I will follow up when done."`

**Expected (follow-up):** `"Done. <filename> ingested — N new chunk(s) stored."`

---

### 3.4 — File too large rejection

Attempt to send a file larger than 10 MB (create one locally if needed):

```bash
dd if=/dev/urandom of=/tmp/large_test.bin bs=1M count=11
```

Send via Telegram with `/ingest` caption.

**Expected:** `"File too large (11 MB). Maximum is 10 MB."` No ingest.processed event.

---

### 3.5 — Duplicate chunk detection

Ingest the same document a second time (repeat step 3.1 with the same file).

**Expected follow-up:** `"Done. <filename> ingested — 0 new chunk(s) stored. (N duplicate chunk(s) skipped.)"`

---

## Section 4 — Query and RAG (Block 8)

### 4.1 — Basic query

Send a question whose answer appears in one of the ingested documents.

Example (if your document contains relevant content):
`"What does the document say about [topic]?"`

**Expected:** CLIVE responds with a relevant, coherent answer drawing from the
ingested content. Response is in CLIVE's personality voice (trusted advisor,
direct).

---

### 4.2 — Query with no matching documents (low-confidence indicator)

Send a question about a topic that is not in any ingested document.

Example: `"What is the population of Mars?"`

**Expected:** CLIVE responds from general knowledge. The response ends with:
`"⚠️ (Answered from general knowledge — no relevant documents found)"` (D-047)

---

### 4.3 — Personality in response

Review the response from 4.1 or 4.2. It should reflect CLIVE's personality
document (D-051, D-052, D-053):
- Direct and concise
- No sycophancy ("Great question!")
- Register adapted to the query
- Trusted advisor tone

---

### 4.4 — Cross-session memory

1. In a fresh conversation, tell CLIVE a fact: `"My favourite colour is burgundy."`
2. Wait for a response.
3. Send `/start` to reset the session.
4. Ask: `"Do you remember what I told you about my favourite colour?"`

**Expected:** CLIVE recalls the fact from the previous session, demonstrating
cross-session memory (D-128/D-130, Block 11).

---

### 4.5 — Conversation context injection

Within a single session (no /start):
1. Ask: `"What is 2 + 2?"`
2. Follow up: `"Multiply that by 3."`

**Expected:** CLIVE correctly uses the context of the prior turn to answer "12".
This validates turn-level context injection (D-115).

---

## Section 5 — Document Deletion (Block 9 / D-006)

### 5.1 — Delete an existing document

Ingest a test document (see Section 3.1) to be used as the deletion target.
Note the filename.

Send: `/delete <filename>`

**Expected:** CLIVE responds with a confirmation prompt:
`"⚠️ Delete <filename> (N chunk(s)). Reply /confirm_delete to proceed or /cancel_delete to abort. (No response within 2 minutes cancels automatically.)"`

---

### 5.2 — Confirm deletion

Send `/confirm_delete`

**Expected:**
- Immediate: `"Confirmed. Deleting..."`
- Follow-up: `"Deleted. <filename> removed (N chunk(s) purged)."`

Send `/list`. The document should no longer appear.

---

### 5.3 — Cancel deletion

Ingest another test document. Send `/delete <filename>`.

When the confirmation prompt appears, send `/cancel_delete`.

**Expected:** `"Deletion cancelled."`

Send `/list`. The document should still be present.

---

### 5.4 — Delete non-existent document

Send: `/delete made_up_filename.txt`

**Expected:** `"No document named made_up_filename.txt found."` (D-106 criterion 4)

---

### 5.5 — Deletion timeout

Send `/delete <filename>`. When the prompt appears, wait >2 minutes without
responding.

**Expected:** CLIVE sends an automatic timeout message:
`"Deletion of <filename> timed out — no response received."` and clears the
pending state (D-006 auto-cancel).

---

## Section 6 — Action Layer — Web Search (Block 9)

### 6.1 — Web search intent detection

Send: `"search for the latest news on AI regulation"`

**Expected:** CLIVE presents a confirmation prompt:
`"⚠️ Search the web for: the latest news on AI regulation. Reply /confirm_action to proceed or /cancel_action to abort."`

---

### 6.2 — Confirm web search

After the prompt from 6.1, send `/confirm_action`

**Expected:** CLIVE executes the search and delivers a summary of results to Telegram.

---

### 6.3 — Cancel web search

Trigger a search intent. When the confirmation prompt appears, send `/cancel_action`.

**Expected:** `"Cancelled."` No search is performed.

---

### 6.4 — Search intent variant

Send: `"look up Python asyncio documentation"`

**Expected:** Confirmation prompt for web search (intent detection also works
with "look up" prefix).

---

## Section 7 — Action Layer — Reminders (Block 9)

### 7.1 — Reminder intent detection

Send: `"remind me to call Tim tomorrow at 9am"`

**Expected:** CLIVE presents a confirmation prompt including the parsed time
and reminder message. The displayed time should reflect the `CLIVE_TIMEZONE`
setting from `secrets.env`.

---

### 7.2 — Confirm reminder

After the prompt from 7.1, send `/confirm_action`

**Expected:** `"Confirmed."` A reminder is scheduled.

---

### 7.3 — Verify reminder fires

(Set a reminder for a few minutes from now for a quick test.)

Send: `"remind me about test reminder in 3 minutes"` → `/confirm_action`

Wait 3 minutes.

**Expected:** CLIVE sends a notification: `"Reminder: test reminder"` (or similar
format) to Telegram at approximately the scheduled time.

---

## Section 8 — Tool Registry (Block 17)

### 8.1 — List tools

Send `/tools`

**Expected:** Response lists all registered tools with name, version, status
(enabled/disabled), and description. At minimum, `web_search` and
`reminder_scheduler` should be listed.

---

### 8.2 — Disable a tool

Send `/tool_disable web_search`

**Expected:** Confirmation prompt:
```
Disable web_search?

Web Search · v1.0
[description]

When disabled, this tool will be unavailable until re-enabled.

/confirm_action — confirm disable
/cancel_action — cancel
```

---

### 8.3 — Confirm tool disable

Send `/confirm_action` after 8.2.

**Expected:** `"web_search disabled."`

Send `/tools` — `web_search` should show as `disabled`.

---

### 8.4 — Verify disabled tool is blocked

Send `"search for AI news"` (triggers web search intent).

**Expected:** CLIVE responds that the web_search tool is unavailable (action
rejected by tool registry gate, D-137). No confirmation prompt is shown.

---

### 8.5 — Re-enable a tool

Send `/tool_enable web_search` → `/confirm_action`

**Expected:** `"web_search enabled."`

Send `/tools` — `web_search` shows as `enabled`.

---

### 8.6 — Cancel tool operation

Send `/tool_disable reminder_scheduler`. When prompt appears, send `/cancel_action`.

**Expected:** `"Cancelled. reminder_scheduler remains enabled."` Tool status unchanged.

---

## Section 9 — Feedback (Block 18)

### 9.1 — Tag a response as poor quality

Send a query. After receiving a response, send `/bad`.

**Expected:** `"Noted. Tagged as poor quality."`

---

### 9.2 — /bad with no prior query

Send `/start` to reset session. Then immediately send `/bad`.

**Expected:** `"No recent retrieval to tag. Send a query first."`

---

### 9.3 — Verify feedback record in DB

On the VM:

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT feedback_id, feedback_type, submitted_at
  FROM clive_state.feedback
  ORDER BY submitted_at DESC
  LIMIT 3;
"
```

**Expected:** One or more rows with `feedback_type = 'poor_quality'` and a
recent `submitted_at` timestamp.

---

## Section 10 — Cost / Rate Management (Block 20)

### 10.1 — LLM spend tracking

Send several queries. After each, send `/status`.

**Expected:** `LLM spend today: $0.XXXX` increases after each query, reflecting
real LLM token usage.

---

### 10.2 — /status shows daily cap

Check the current daily cap configuration. If a cap is set in `secrets.env`
(`DAILY_SPEND_CAP_USD`), `/status` should show:
`"Daily cap: $X.XXXX"`

If no cap is set: `"Daily cap: no cap set"`

---

### 10.3 — Rate limit enforcement

If `RATE_LIMIT_QUERIES_PER_HOUR` is set in `secrets.env` to a small number
(e.g. 2), send queries until the limit is reached.

**Expected:** After the limit is hit, CLIVE responds:
`"Rate limit reached for this hour. Please try again next hour."`

(Reset by waiting for the next clock hour, or temporarily increasing the limit.)

---

## Section 11 — Workers / Scheduler (Block 10)

### 11.1 — Worker configuration in DB

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT worker_name, cron_expression, schedule_type
  FROM clive_state.workers;
"
```

**Expected:** Rows for `daily_digest` and `knowledge_maintenance` with valid
cron expressions.

---

### 11.2 — Worker runs recorded

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT worker_name, status, triggered_at, completed_at
  FROM clive_state.worker_runs
  ORDER BY triggered_at DESC
  LIMIT 5;
"
```

**Expected:** If the scheduler has been running, rows showing worker runs with
status `success` or `running`.

---

### 11.3 — Scheduler is alive

Check orchestrator logs for scheduler activity:

```bash
docker logs clive-orchestrator --since 1h | grep scheduler
```

**Expected:** Log lines containing `scheduler_started` and/or `worker_starting`
events in JSON format.

---

### 11.4 — Daily digest notification (manual trigger test)

This test may require temporarily overriding the cron schedule or triggering the
worker manually. If the worker has already run today, check orchestrator logs.

```bash
docker logs clive-orchestrator --since 24h | grep '"worker_name": "daily_digest"'
```

**Expected:** Log line showing `daily_digest` worker run with `status=success`.

---

## Section 12 — Web Dashboard (Blocks 2 / 3 / 4 / 5)

### 12.1 — Login

Navigate to `https://clive.halmshaw.co.uk` in a browser.

**Expected:** Login page is served. Enter the dashboard password (`DASHBOARD_SECRET`).

**Expected:** Successful login redirects to the dashboard main page.

---

### 12.2 — Dashboard loads

After login, the dashboard should display:
- Input field for sending queries
- Conversation history area (may be empty)
- Any pending action confirmations

**Expected:** Dashboard renders without JavaScript errors (check browser console).

---

### 12.3 — Send a query from the dashboard

Type a question in the dashboard input and submit it.

**Expected:** The query is sent. Within a few seconds, CLIVE's response appears
in the conversation area on the dashboard.

**Also verify:** No response is sent to Telegram for this query. Dashboard
queries carry `source_surface="dashboard"` and Block 4 routes responses back
to the dashboard only (D-146).

---

### 12.4 — Conversation history

Send 3–4 queries from the dashboard. Navigate away and back to the dashboard.

**Expected:** History of prior turns is displayed.

---

### 12.5 — Delete document from dashboard

Send a query that will trigger a deletion flow (or send `/delete <filename>`
via Telegram to generate a pending action). Open the dashboard.

**Expected:** The pending action confirmation is visible in the dashboard.
Click confirm on the dashboard.

**Expected:** The deletion proceeds. The confirmation is cleared from the dashboard.

---

### 12.6 — Dual-surface routing

With both Telegram and the dashboard open simultaneously:
1. Send a query from Telegram
2. Send a query from the dashboard

**Expected:**
- Telegram query response is delivered to Telegram only
- Dashboard query response is delivered to the dashboard only
- No cross-surface leakage (D-146)

---

### 12.7 — Logout

Click logout on the dashboard.

**Expected:** Session is cleared. Navigating to `/api/history` returns 401 or
redirect to login. Cookie is cleared.

---

### 12.8 — Session persistence

Log in to the dashboard. Close the browser tab. Reopen `https://clive.halmshaw.co.uk`.

**Expected:** Still logged in (session cookie persists for 30 days per D-147 AC-3).

---

### 12.9 — Unauthenticated API access rejected

From a terminal (without a session cookie):

```bash
curl -sf https://clive.halmshaw.co.uk/api/history
```

**Expected:** HTTP 401 or 403 — API endpoints require an authenticated session.

---

## Section 13 — System Documents (Block 1 + Block 16)

### 13.1 — Personality document is active

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT document_type, version_id, is_active, created_at
  FROM clive_state.system_documents
  WHERE document_type = 'personality' AND is_active = true;
"
```

**Expected:** Exactly one row with `is_active = true`.

---

### 13.2 — Alignment rules document is active

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT document_type, version_id, is_active
  FROM clive_state.system_documents
  WHERE document_type = 'alignment_rules' AND is_active = true;
"
```

**Expected:** Exactly one row with `is_active = true`.

---

### 13.3 — System document two-step activation (D-079)

1. Use the seed script or direct DB insert to load a new (inactive) personality
   document:

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  INSERT INTO clive_state.system_documents
    (version_id, document_type, document_content, zone_scope, is_active)
  VALUES
    (gen_random_uuid(), 'personality', 'Test personality content.', 'personal', false);
"
```

2. On Telegram, send `/activate personality`

**Expected:** CLIVE shows the version_id and a 200-character preview, then
prompts: `"Reply /confirm_activate <version_id> to activate."`

3. Send `/confirm_activate <version_id>` (using the exact version_id shown)

**Expected:** `"Activated. personality v<version_id> is now live."`

4. Verify in DB:

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT version_id, is_active FROM clive_state.system_documents
  WHERE document_type = 'personality' ORDER BY created_at DESC LIMIT 3;
"
```

**Expected:** The new version_id has `is_active = true`. The previous version
has `is_active = false`.

After testing, restore the correct personality document the same way.

---

## Section 14 — Config / Admin (Block 19)

### 14.1 — Set spend cap via conversational admin

CLIVE supports setting the daily LLM spend cap via a configured conversational
workflow. Check the config_handler for how this is triggered.

Send the trigger phrase (from the config_handler implementation):
`"set spend cap to $2.00"` or equivalent, then confirm.

**Expected:** `/status` shows `"Daily cap: $2.0000"` after confirmation.

---

### 14.2 — Reschedule a worker

Trigger the worker reschedule workflow to change a cron expression:

```
"reschedule daily_digest to run at 8am"
```

Then confirm. Verify in DB:

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT worker_name, cron_expression FROM clive_state.workers
  WHERE worker_name = 'daily_digest';
"
```

**Expected:** Cron expression updated to reflect the new schedule.

---

## Section 15 — Observability (Block 25)

### 15.1 — Alloy is running and scraping

Check Alloy logs for scraping activity:

```bash
docker logs clive-alloy --since 5m | grep -i scrape
```

**Expected:** Log lines showing metrics being scraped from CLIVE services.

---

### 15.2 — Grafana Cloud receives metrics

Log into Grafana Cloud (grafana.com, project associated with `cliveai@proton.me`).

Navigate to Explore → Metrics. Query `clive_events_total` or `clive_query_total`.

**Expected:** Data points from the last 24 hours. Time series charts show
activity.

---

### 15.3 — Grafana Cloud receives logs

In Grafana Cloud → Explore → Logs. Query `{container_name="clive-orchestrator"}`.

**Expected:** JSON log lines from the orchestrator, including `event_type`
fields from the event bus (D-134). Lines are parseable by Loki's JSON parser.

---

### 15.4 — Alert routing via orchestrator

Verify the alert routing path is wired (D-118). Check orchestrator subscribers:

```bash
docker logs clive-orchestrator | grep "alert"
```

**Expected:** `ALERT_TRIGGERED` is subscribed to by Block 23's push handler
(`push_alert_to_surface`). Alert events from Grafana Alertmanager would route
via the orchestrator webhook to Telegram.

---

### 15.5 — Node metrics visible

In Grafana Cloud, query `node_cpu_seconds_total` or `node_memory_MemFree_bytes`.

**Expected:** Host-level metrics are present and current (node-exporter is running).

---

### 15.6 — Postgres metrics visible

In Grafana Cloud, query `pg_stat_database_tup_fetched`.

**Expected:** PostgreSQL metrics are present (postgres-exporter is running).

---

## Section 16 — Alignment and Security (Blocks 22 / 23 / 6 / 7 / 24)

### 16.1 — Alignment gate: destructive action requires confirmation

Every deletion in Section 5 confirmed this. Verify that no deletion was
executed without the owner sending `/confirm_delete` (D-006). Review any
deletion result in Section 5 — confirm it required an explicit confirm step.

---

### 16.2 — Alignment gate: personality protection

Verify in `alignment.py` that evolution events targeting Block 1 (Personality)
are rejected. This is a code-review test (no runtime path to trigger it in v1
without Block 21 active). Confirm the `BLOCK_PERSONALITY = 1` guard is present
and the `evolution_targeting_personality_block` reason code is defined.

```bash
docker exec clive-orchestrator cat /app/orchestrator/alignment.py | grep BLOCK_PERSONALITY
```

**Expected:** `BLOCK_PERSONALITY = 1` and the evolution rejection rule is present.

---

### 16.3 — Alignment gate: deception check

The alignment gate rejects events where `declared_event_type` does not match
`event_type`. This is enforced in `_check_standard`. Confirm via unit test logs
that this check is covered:

```bash
grep -r "declared_intent_mismatch" /Users/timhalmshaw/dev/clive/src/orchestrator/tests/
```

**Expected:** At least one test covering this alignment rule.

---

### 16.4 — Sandboxing stub: production guard

The sandboxing package must not be imported by any running service:

```bash
docker exec clive-orchestrator python3 -c "
from orchestrator import alignment, bus, action
import sys
assert 'sandboxing' not in sys.modules, 'sandboxing imported in production'
print('sandboxing_not_imported: OK')
"
```

**Expected:** `sandboxing_not_imported: OK`

Also verify `SANDBOXING_ACTIVE=False` in the stub:

```bash
python3 -c "from sandboxing import SANDBOXING_ACTIVE; print(SANDBOXING_ACTIVE)" 2>/dev/null || echo "package not installed in this env"
```

In the sandboxing package source:

```bash
grep "SANDBOXING_ACTIVE" /Users/timhalmshaw/dev/clive/src/sandboxing/__init__.py
```

**Expected:** `SANDBOXING_ACTIVE = False`

---

### 16.5 — DB role privileges

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  SELECT grantee, privilege_type, table_schema, table_name
  FROM information_schema.role_table_grants
  WHERE grantee IN ('clive_audit_writer', 'clive_app')
  ORDER BY grantee, table_schema, table_name, privilege_type;
"
```

**Expected:**
- `clive_audit_writer`: `INSERT` and `SELECT` on `clive_audit.event_log` only.
  No `UPDATE` or `DELETE`.
- `clive_app`: `SELECT, INSERT, UPDATE, DELETE` on application tables in
  `clive_search` and `clive_state`.
- `clive_state.config`: `SELECT, INSERT, UPDATE` only — no `DELETE`.

---

### 16.6 — No hardcoded secrets in source

```bash
grep -rn "ANTHROPIC_API_KEY\|TELEGRAM_BOT_TOKEN\|APP_DB_PASSWORD" \
  /Users/timhalmshaw/dev/clive/src/ \
  --include="*.py" \
  | grep -v ".venv" \
  | grep -v "os.environ\|getenv\|load_dotenv\|env_file\|PLACEHOLDER\|example\|NOSONAR"
```

**Expected:** No output — no hardcoded secret values. All secrets accessed via
`os.environ.get()` or environment injection.

---

### 16.7 — Dashboard session cookie is httponly

Log in to `https://clive.halmshaw.co.uk`. Open browser DevTools → Application
→ Cookies.

**Expected:** The `session` cookie has `HttpOnly` flag set. It is not accessible
via JavaScript (protects against XSS session theft).

---

### 16.8 — Dashboard auth guard: DASHBOARD_SECRET must be set

On the VM, temporarily check what happens if the secret is absent (do NOT
actually remove it — just review the auth code):

```bash
grep "DASHBOARD_SECRET" /Users/timhalmshaw/dev/clive/src/dashboard/clive_dashboard/auth.py
```

**Expected:** Code raises `RuntimeError` if `DASHBOARD_SECRET` is absent at
startup. This prevents the dashboard starting with no auth.

---

## Section 17 — End-to-End Flows

### 17.1 — Ingest → Query → Answer

1. Ingest a document containing a specific fact (e.g. "The capital of France is Paris.")
2. Wait for ingest confirmation
3. Send query: `"What is the capital of France?"` (or matching the document)
4. Verify CLIVE returns the correct answer drawn from the document

**Expected:** Full pipeline — Telegram → Block 13 → Block 15 → Block 8 → Block 16 →
LLM → Block 13 → Telegram — completes correctly and the answer is grounded in the document.

---

### 17.2 — Delete → Query → Fallback to general knowledge

After 17.1:

1. Delete the document via `/delete <filename>` → `/confirm_delete`
2. Wait for deletion confirmation
3. Send the same query again

**Expected:** CLIVE answers from general knowledge (the document is gone from
the vector index) and includes the low-confidence indicator:
`"⚠️ (Answered from general knowledge — no relevant documents found)"`

---

### 17.3 — Dual-surface query

1. Log in to the dashboard
2. Open Telegram
3. Send from Telegram: `"What is today's date?"`
4. Send from dashboard: `"What is the meaning of life?"`

**Expected:**
- Telegram response delivered to Telegram only
- Dashboard response delivered to dashboard only
- Verify no overlap — the Telegram question doesn't appear in the dashboard
  conversation and vice versa

---

### 17.4 — Cross-session entity memory

1. In a new Telegram session (`/start`), tell CLIVE: `"My dog is called Biscuit."`
2. Send `/start` to reset
3. Ask: `"What is my dog called?"`

**Expected:** CLIVE remembers `Biscuit` from the previous session via Block 11
entity/fact extraction and semantic retrieval (D-128/D-130).

---

## Section 18 — CI / CD Verification

### 18.1 — Unit tests pass

Trigger the CI pipeline via GitHub Actions:

```
.github/workflows/ci.yml
```

Or run locally for each service:

```bash
cd /Users/timhalmshaw/dev/clive/src/orchestrator && python -m pytest tests/ -v --tb=short
cd /Users/timhalmshaw/dev/clive/src/query && python -m pytest tests/ -v --tb=short
cd /Users/timhalmshaw/dev/clive/src/telegram && python -m pytest tests/ -v --tb=short
cd /Users/timhalmshaw/dev/clive/src/processing && python -m pytest tests/ -v --tb=short
cd /Users/timhalmshaw/dev/clive/src/dashboard && python -m pytest tests/ -v --tb=short
```

**Expected:** All tests pass. No test failures.

---

### 18.2 — SQL idempotency tests

The CI pipeline runs SQL init scripts twice and verifies idempotency (D-095).
Confirm by reviewing the CI run output. Key requirement: no SQL script fails on
re-run. Look for `CREATE IF NOT EXISTS` and `ON CONFLICT DO NOTHING` patterns.

```bash
grep -l "IF NOT EXISTS\|ON CONFLICT DO NOTHING" \
  /Users/timhalmshaw/dev/clive/infrastructure/sql/init/*.sql
```

**Expected:** Every SQL init file uses idempotent patterns.

---

### 18.3 — Rollback workflow available

Verify the rollback workflow is accessible:

```bash
cat /Users/timhalmshaw/dev/clive/.github/workflows/rollback.yml | grep "runs-on"
```

**Expected:** Runs on `self-hosted` runner. Rollback is available as a manual
dispatch action if a bad deploy needs reverting.

---

## Section 19 — Cleanup

After completing all test sections:

1. Delete any test documents ingested during testing (if not already cleaned up in Section 5):

```bash
# Via Telegram: /delete <test_filename>  → /confirm_delete
```

2. Re-enable any tools disabled during testing (Section 8.3):

```bash
# Via Telegram: /tool_enable web_search  → /confirm_action
```

3. Remove any test feedback records (optional — they are low-risk):

```bash
docker exec clive-postgres psql -U postgres -d clive -c "
  DELETE FROM clive_state.feedback WHERE submitted_at > NOW() - INTERVAL '1 day';
"
```

4. If the personality document was replaced in Section 13.3, restore the original:

```
/activate personality → /confirm_activate <original_version_id>
```

5. Reset spend cap if changed in Section 14.1 to avoid blocking real usage.

---

## Pass / Fail Criteria

The v1.0 system test passes when **all the following are true:**

| # | Criterion |
|---|-----------|
| 1 | All containers healthy (Section 1.1) |
| 2 | Public HTTPS endpoint reachable with valid TLS (Section 1.3) |
| 3 | All Telegram commands respond correctly (Section 2) |
| 4 | Ingest pipeline: desktop + mobile both complete successfully (Section 3.1, 3.3) |
| 5 | Query returns relevant answer from ingested documents (Section 4.1) |
| 6 | Low-confidence indicator shown when no relevant docs (Section 4.2) |
| 7 | Cross-session memory recalls facts from prior session (Section 4.4) |
| 8 | Deletion requires explicit confirmation and succeeds (Section 5.1–5.2) |
| 9 | Deletion timeout auto-cancels (Section 5.5) |
| 10 | Web search confirmation gate works end-to-end (Section 6.1–6.2) |
| 11 | Reminder fires at scheduled time (Section 7.3) |
| 12 | Tool disable/enable routes through confirmation gate (Section 8.2–8.5) |
| 13 | Disabled tool is blocked from execution (Section 8.4) |
| 14 | /bad tags retrieval and feedback persists to DB (Section 9.1, 9.3) |
| 15 | LLM spend tracked and reported in /status (Section 10.1) |
| 16 | Dashboard login, query, and response all work (Section 12.1–12.3) |
| 17 | Dual-surface routing: no cross-surface leakage (Section 12.6) |
| 18 | System documents activate via two-step flow (Section 13.3) |
| 19 | Audit log rejects UPDATE from audit_writer role (Section 1.6) |
| 20 | Sandboxing inactive in production (Section 16.4) |
| 21 | No hardcoded secrets in source (Section 16.6) |
| 22 | CI unit tests pass (Section 18.1) |
| 23 | SQL scripts idempotent (Section 18.2) |
| 24 | Grafana Cloud receives metrics and logs (Section 15.2–15.3) |

Any **FAIL** on criteria 1–21 blocks sign-off. Criteria 22–24 are strong
requirements but may be deferred 24h for an infrastructure-only issue that
does not affect runtime correctness.

---

## Known Limitations (Not Blocking)

| Limitation | Decision | Notes |
|---|---|---|
| SSH open to `0.0.0.0/0` | D-154 AC-7 | P3 only — key auth enforced, acceptable for personal system |
| No staging environment | D-074 | CI deploys direct to production — owner accepted |
| 24h max data loss window | D-056 | Nightly snapshot backup only |
| Single orchestrator instance, no redundancy | D-023 | Single VM design, owner accepted |
| Block 21 (Evolution Engine) gated | D-042 | Unblocked for v2 per D-154 |
| Block 26 (Physical Device) gated | D-135 | Hardware readiness decision pending |

---

*CLIVE v1.0 System Test Plan — maintained in `docs/`*  
*Architect sign-off required on any modification to pass/fail criteria.*
