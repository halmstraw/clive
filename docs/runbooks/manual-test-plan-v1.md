# CLIVE v1.0 — Manual Test Plan

**Purpose:** Verify the full production system after the v0.12 + v1.0 deployment.
Run these tests in order. Each section states what to send, what to expect, and
what failure looks like.

**Surfaces:** Telegram (primary) and web dashboard at clive.halmshaw.co.uk.

**Time required:** ~30 minutes for the full plan. ~10 minutes for core only.

---

## 0 — Pre-flight

Before testing anything, confirm the stack is healthy.

### 0.1 Container health

SSH to the VM (or check Grafana) and run:

```bash
docker compose ps
```

**Expected:** All services show `healthy` or `running`. No restarts in the last
10 minutes. Services: orchestrator, query, telegram, processing, dashboard,
postgres, minio, prometheus, loki, promtail, grafana, caddy, node-exporter,
postgres-exporter.

**If unhealthy:** Check `docker compose logs <service> --tail 50`.

### 0.2 Grafana dashboard

Open `https://grafana.halmshaw.co.uk`. Log in.

**Expected:** CLIVE Event Bus dashboard loads. No red alerts firing.

### 0.3 /status baseline

In Telegram, send:

```
/status
```

**Expected:** Response shows today's spend (probably $0.00 if fresh deploy),
document count, last ingest time, daily cap (if set). No error message.
Note the document count — you'll use it later.

---

## 1 — Core query (Block 8 regression)

### 1.1 Simple factual query

Send a question about something you've ingested:

```
[any question your documents can answer]
```

**Expected:** CLIVE responds with a relevant answer, personality intact (direct,
no waffle). Confidence should be reasonable. No "I don't have information" if
the document clearly covers it.

### 1.2 Query about something not in knowledge base

```
What is the population of Iceland?
```

**Expected:** CLIVE responds helpfully from general knowledge or says it doesn't
have that in its knowledge base. It does not hallucinate a document source.

### 1.3 Conversation memory (Block 11)

Send two messages in the same conversation:

```
My favourite colour is blue.
```

Wait for response, then:

```
What did I just tell you?
```

**Expected:** CLIVE recalls you mentioned blue. Demonstrates cross-turn memory
within the session.

---

## 2 — Self-knowledge queries (Block 29 — new in v0.12)

These all short-circuit the RAG pipeline and answer from live system state.
The `/list`, `/tools`, `/status` commands are unchanged — these are the
conversational equivalents.

### 2.1 Documents query

```
What documents do you know about?
```

**Expected:** Natural language list of your ingested documents with filenames
and chunk counts. Should match what `/list` returns. No vector search invoked.

### 2.2 Tools query

```
What tools do you have?
```

**Expected:** Natural language description of available tools from the tool
registry (web search, reminder, delete, plus any workers). Should match
`/tools` output.

### 2.3 Actions query

```
What actions have you taken this week?
```

**Expected:** Summary of recent confirmed/cancelled actions from the last 7
days. If you haven't taken any actions, it should say so clearly rather than
erroring.

### 2.4 Workers query

```
What background tasks do you run?
```

**Expected:** List of registered workers (daily digest, knowledge maintenance)
with their schedules and last-run times.

### 2.5 Health query (conversational /status)

```
How much have you cost today?
```

**Expected:** Natural language health summary: spend, cap (if set), document
count, last ingest. Should match `/status` data.

```
What's your system status?
```

**Expected:** Same data, different phrasing. Both should work.

---

## 3 — Conversational config (Block 19 — new in v0.12)

These route through Block 9's confirmation gate. You must confirm each one.

### 3.1 Set spend cap conversationally

Send:

```
Set my daily spend cap to $3
```

**Expected:**
1. CLIVE sends a confirmation request: "Set daily spend cap to $3.00 —
   confirm with /confirm_action or cancel with /cancel_action."
2. Send `/confirm_action`.
3. CLIVE confirms the change.
4. Send `/status` — verify daily cap now shows $3.00.

**Verify persistence:** The cap should survive a process restart (it's in the
database, not just env var). You can check by running
`docker compose restart orchestrator` and then `/status` again.

### 3.2 Cancel a config change

Send:

```
Set my daily spend cap to $0.01
```

**Expected:** Confirmation request sent.

Send `/cancel_action`.

**Expected:** CLIVE confirms cancellation. `/status` still shows $3.00 (or
whatever you set in 3.1), not $0.01.

### 3.3 Reschedule a worker

Send:

```
Run the daily digest at 9am
```

**Expected:**
1. Confirmation request: "Reschedule daily_digest to run at 0 9 * * * —
   confirm or cancel."
2. Send `/confirm_action`.
3. CLIVE confirms. The worker's schedule in the tool registry is now updated.

**Verify:** Send "what background tasks do you run?" — the daily digest should
show the updated schedule.

### 3.4 Reset spend cap to something sensible

After testing, reset:

```
Set my daily spend cap to $10
```

Confirm with `/confirm_action`. Verify with `/status`.

---

## 4 — Ingestion pipeline (Block 14/15 regression)

### 4.1 Mobile ingest (document upload)

On mobile Telegram, send any PDF or text file (not as a photo — as a file).

**Expected:**
1. CLIVE responds: "Document received. Send /ingest_confirm to ingest, or
   ignore to discard."
2. Send `/ingest_confirm`.
3. CLIVE confirms ingestion with filename and chunk count.
4. Run "what documents do you know about?" — new document appears.

### 4.2 Document list

```
/list
```

**Expected:** List of all ingested documents. Count should be one more than
your pre-flight baseline (from 0.3).

---

## 5 — Deletion (Block 9 regression)

### 5.1 Delete a test document

Pick a document name from `/list`. Send:

```
/delete [filename]
```

**Expected:**
1. Confirmation request: "Delete [filename]? Send /confirm_delete or
   /cancel_delete."
2. Send `/confirm_delete`.
3. CLIVE confirms deletion.
4. `/list` — document is gone.

---

## 6 — Action layer (Block 9 regression)

### 6.1 Web search

```
Search the web for the latest news about Claude AI
```

**Expected:**
1. Confirmation request: "Search the web for: latest news about Claude AI —
   confirm or cancel."
2. `/confirm_action`.
3. CLIVE returns search results summary.

### 6.2 Reminder

```
Remind me to check the CLIVE deployment in 2 minutes
```

**Expected:**
1. Confirmation request with parsed time.
2. `/confirm_action`.
3. CLIVE confirms reminder is scheduled.
4. Wait 2 minutes — reminder fires via Telegram.

---

## 7 — Feedback (Block 18 regression)

After any query response you're not happy with:

```
/bad
```

**Expected:** CLIVE acknowledges the feedback. (Internally: the most recent
retrieval is tagged as poor quality in `clive_state.feedback`.)

---

## 8 — Access control (Block 6/7 regression)

### 8.1 /whoami

```
/whoami
```

**Expected:** Returns your user profile — Telegram ID, role (owner), zone
access (personal). Confirms the user record is intact.

---

## 9 — Web dashboard (Block 2 regression)

Open `https://clive.halmshaw.co.uk`.

### 9.1 Login

Enter your `DASHBOARD_SECRET`. Click login.

**Expected:** Redirected to dashboard home. Session cookie set. No 401.

### 9.2 Submit a query from dashboard

Type a question in the query box. Submit.

**Expected:** Response appears. Same quality as Telegram responses.

### 9.3 Shared conversation history

After the dashboard query, go to Telegram and check recent conversation history
(if your dashboard shows history, verify the dashboard query appears there too,
and Telegram queries appear in dashboard history).

### 9.4 Pending actions visible from dashboard

Trigger an action from Telegram (e.g. web search) but don't confirm it yet.
Open the dashboard `/api/pending` (or the pending actions panel if the frontend
shows it).

**Expected:** The pending action is visible. You can confirm or cancel from
the dashboard — not only from Telegram.

---

## 10 — Observability (Block 25 regression)

### 10.1 Event bus dashboard

In Grafana, open the CLIVE Event Bus dashboard. After running the tests above,
you should see:

- Events dispatched across multiple types (query.received, query.response,
  action.pending, action.confirmed, etc.)
- No sustained error rate
- Latency within expected range

### 10.2 Alert test (optional)

In Grafana, check that no alerts are currently firing. If you want to test
alert routing, you can temporarily lower a threshold, trigger it, and verify
the alert message arrives in Telegram.

---

## 11 — Block 24 stub verification (v1.0)

This is a negative test — verify the sandbox is NOT active.

### 11.1 Sandbox service not running

On the VM:

```bash
docker compose ps sandbox
```

**Expected:** The sandbox service is not listed (or shows as not running). It
should only start with `--profile experimental`.

### 11.2 Confirm production guard

This is verifiable in the codebase but can't be tested via Telegram. The
relevant check is `SANDBOXING_ACTIVE = False` in `src/sandboxing/types.py`.
No production code path imports or calls the sandboxing package.

---

## Pass criteria

The test run passes when:

- [ ] All /status, /list, /tools, /help, /whoami commands return correct output
- [ ] Conversational self-knowledge works for all five intents (documents, tools,
      actions, workers, health)
- [ ] Spend cap set conversationally persists after process restart
- [ ] Worker reschedule updates the schedule in the registry
- [ ] Cancellation of config changes leaves state unchanged
- [ ] At least one document ingested and queryable
- [ ] At least one deletion confirmed and document removed from list
- [ ] Web search and reminder actions work end-to-end
- [ ] Dashboard login, query, and history work
- [ ] Grafana event bus dashboard shows activity
- [ ] Sandbox service is not running

---

## If something fails

1. Check `docker compose logs <service> --tail 100` for the relevant service.
2. Check Grafana Loki for the event stream around the failure time.
3. If the failure is in a new v0.12 or v1.0 feature, check the relevant
   decision: D-149 (v0.12 scope), D-152 (v1.0 scope).
4. For config handler failures: check `clive_state.config` and `clive_state.audit_log`
   directly in psql.
5. For self-knowledge failures: the orchestrator log will show which endpoint
   was called and whether it returned data.

---

*Manual test plan for CLIVE v1.0. Run after any major deployment.*
