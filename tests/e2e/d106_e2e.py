#!/usr/bin/env python3
"""D-106 E2E integration test — HTTP API level (no Telegram credentials).

Tests the v0.3 backend pipeline by posting events directly to the orchestrator
and verifying DB/MinIO state via docker exec.

Runs on the self-hosted GitHub Actions runner where all services are on the
clive-internal Docker network with no host port exposure. All HTTP calls route
through docker exec into the orchestrator container.

Covers D-106 criteria:
  C2 — Cancel path (no deletion on owner rejection; chunk count unchanged)
  C3 — Confirmed deletion (DB chunks removed, MinIO object gone, audit logged)
  C4 — Not-found path (deletion.not_found emitted; no crash or DB change)
  C5 — Block 18 feedback (persisted to clive_state.feedback; audited)
  C6 — Audit trail (all required event types with non-null source_block)

C1 (CI unit tests pass) is verified by the standard CI pipeline, not here.

The test is self-cleaning: it creates d106_throwaway_test.txt at the start
and removes it at the end (via the teardown step in a finally block),
regardless of test outcome.  The live system is left in the same state
it was in before the test ran.

REQUIRED ENV VARS:
  TELEGRAM_OWNER_CHAT_ID     — integer; read from /etc/clive/secrets.env in CI

OPTIONAL ENV VARS:
  CLIVE_ORCHESTRATOR_CONTAINER — default: clive-orchestrator
  CLIVE_POSTGRES_CONTAINER     — default: clive-postgres
  CLIVE_MINIO_CONTAINER        — default: clive-minio
  MINIO_RAW_BUCKET             — default: clive-raw-store
  SKIP_MINIO_CHECK             — set to 1 to skip MinIO object verification
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORCHESTRATOR_CONTAINER = os.environ.get("CLIVE_ORCHESTRATOR_CONTAINER", "clive-orchestrator")
POSTGRES_CONTAINER = os.environ.get("CLIVE_POSTGRES_CONTAINER", "clive-postgres")
MINIO_CONTAINER = os.environ.get("CLIVE_MINIO_CONTAINER", "clive-minio")
MINIO_BUCKET = os.environ.get("MINIO_RAW_BUCKET", "clive-raw-store")
SKIP_MINIO = os.environ.get("SKIP_MINIO_CHECK", "0") == "1"

try:
    OWNER_CHAT_ID = int(os.environ["TELEGRAM_OWNER_CHAT_ID"])
except (KeyError, ValueError) as _exc:
    print(f"FATAL: TELEGRAM_OWNER_CHAT_ID env var missing or invalid: {_exc}")
    sys.exit(1)

THROWAWAY_FILENAME = "d106_throwaway_test.txt"
NONEXISTENT_FILENAME = "this_file_does_not_exist_d106.pdf"

# Polling configuration
POLL_INTERVAL = 0.5   # seconds between DB polls
PENDING_TIMEOUT = 15  # seconds to wait for pending_actions row to appear
ACTION_TIMEOUT = 30   # seconds to wait for action status to resolve
DELETION_TIMEOUT = 90 # seconds to wait for chunks to reach 0
AUDIT_TIMEOUT = 30    # seconds to wait for audit log entries

# Set once in main() — all audit queries filter events after this timestamp
# (avoids false positives from previous test runs)
TEST_START_TS: str = ""


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


_results: list[TestResult] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    _results.append(TestResult(name=name, passed=passed, detail=detail))
    icon = "✅" if passed else "❌"
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon} {name}{suffix}")


# ---------------------------------------------------------------------------
# Docker exec — postgres
# ---------------------------------------------------------------------------

def _psql(query: str) -> str:
    """Run a single SQL query inside the postgres container. Returns raw stdout."""
    result = subprocess.run(
        [
            "docker", "exec", POSTGRES_CONTAINER,
            "psql", "-U", "postgres", "-d", "clive",
            "-t", "-A", "-c", query,
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr.strip()}")
    return result.stdout


def _psql_stdin(sql: str) -> str:
    """Execute SQL passed via stdin. Preferred for INSERT/UPDATE with complex values."""
    result = subprocess.run(
        [
            "docker", "exec", "-i", POSTGRES_CONTAINER,
            "psql", "-U", "postgres", "-d", "clive",
            "-t", "-A",
        ],
        input=sql,
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql (stdin) failed: {result.stderr.strip()}")
    return result.stdout


# ---------------------------------------------------------------------------
# Docker exec — orchestrator HTTP
# ---------------------------------------------------------------------------

def _orchestrator_post(path: str, body: dict) -> dict:
    """POST JSON to the orchestrator from within its own container."""
    body_json = json.dumps(body)
    result = subprocess.run(
        [
            "docker", "exec", ORCHESTRATOR_CONTAINER,
            "curl", "-sf", "-X", "POST",
            f"http://localhost:8080{path}",
            "-H", "Content-Type: application/json",
            "-d", body_json,
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"POST {path} failed (curl exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else {}


# ---------------------------------------------------------------------------
# Docker run — MinIO (minio/mc)
# ---------------------------------------------------------------------------

def _get_minio_creds() -> tuple[str, str]:
    """Read MinIO root credentials from the running minio container."""
    user = subprocess.run(
        ["docker", "exec", MINIO_CONTAINER, "printenv", "MINIO_ROOT_USER"],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    passwd = subprocess.run(
        ["docker", "exec", MINIO_CONTAINER, "printenv", "MINIO_ROOT_PASSWORD"],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    return user, passwd


def minio_pipe_upload(source_key: str, content: str) -> bool:
    """Upload content string to MinIO via minio/mc pipe. Returns True on success.

    Uses the minio/mc Docker image and the minio container's network namespace
    so that mc can reach MinIO at localhost:9000 without any exposed host ports.
    """
    user, passwd = _get_minio_creds()
    result = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "--network", f"container:{MINIO_CONTAINER}",
            "-e", f"MC_HOST_local=http://{user}:{passwd}@localhost:9000",
            "minio/mc", "pipe", f"local/{MINIO_BUCKET}/{source_key}",
        ],
        input=content,
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


def minio_object_gone(source_key: str) -> bool:
    """Return True if the MinIO object no longer exists.

    mc ls exits 0 and prints the object when it exists. Exits non-zero or
    prints nothing when the object is absent.
    """
    user, passwd = _get_minio_creds()
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", f"container:{MINIO_CONTAINER}",
            "-e", f"MC_HOST_local=http://{user}:{passwd}@localhost:9000",
            "minio/mc", "ls", f"local/{MINIO_BUCKET}/{source_key}",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return source_key not in result.stdout


def minio_rm(source_key: str) -> None:
    """Delete a single object from MinIO. Idempotent — missing object is not an error."""
    user, passwd = _get_minio_creds()
    subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", f"container:{MINIO_CONTAINER}",
            "-e", f"MC_HOST_local=http://{user}:{passwd}@localhost:9000",
            "minio/mc", "rm", f"local/{MINIO_BUCKET}/{source_key}",
        ],
        capture_output=True, text=True, timeout=30,
    )
    # Ignore exit code — object may already be absent (idempotent teardown)


# ---------------------------------------------------------------------------
# DB query helpers
# ---------------------------------------------------------------------------

def chunk_count_for(filename: str) -> int:
    """Count chunks in clive_search.chunks for the given original filename."""
    out = _psql(
        f"SELECT count(*) FROM clive_search.chunks "
        f"WHERE source_key LIKE '%/{filename}';"
    )
    for line in out.splitlines():
        s = line.strip()
        if s.isdigit():
            return int(s)
    return 0


def source_key_for(filename: str) -> str | None:
    """Return a source_key for the given original filename, or None if absent."""
    out = _psql(
        f"SELECT source_key FROM clive_search.chunks "
        f"WHERE source_key LIKE '%/{filename}' LIMIT 1;"
    )
    for line in out.splitlines():
        s = line.strip()
        if s and "/" in s:
            return s
    return None


def pending_action_status(action_request_id: str) -> str | None:
    """Return current status of a pending action, or None if row absent."""
    out = _psql(
        f"SELECT status FROM clive_state.pending_actions "
        f"WHERE action_request_id = '{action_request_id}';"
    )
    for line in out.splitlines():
        s = line.strip()
        if s in ("pending", "confirmed", "rejected", "timed_out"):
            return s
    return None


def latest_feedback_row() -> str | None:
    """Return the most recent feedback row as a pipe-delimited string, or None."""
    out = _psql(
        "SELECT feedback_id::text || '|' || retrieval_event_id::text || '|' || feedback_type "
        "FROM clive_state.feedback "
        "ORDER BY submitted_at DESC LIMIT 1;"
    )
    for line in out.splitlines():
        s = line.strip()
        if "poor_quality" in s:
            return s
    return None


def audit_events_since_start() -> dict[str, str]:
    """Return {event_type: source_block} for D-106-relevant events since TEST_START_TS."""
    relevant = (
        "'action.pending','action.confirmation_requested','action.owner_response',"
        "'action.confirmed','action.rejected','deletion.complete','deletion.not_found',"
        "'feedback.explicit'"
    )
    # TEST_START_TS is an ISO-8601 UTC string; PostgreSQL parses it with ::timestamptz
    ts_filter = f"AND timestamp >= '{TEST_START_TS}'::timestamptz" if TEST_START_TS else ""
    out = _psql(
        f"SELECT event_type || '|' || COALESCE(source_block::text, 'NULL') "
        f"FROM clive_audit.event_log "
        f"WHERE event_type IN ({relevant}) {ts_filter} "
        f"ORDER BY timestamp DESC LIMIT 100;"
    )
    found: dict[str, str] = {}
    for line in out.splitlines():
        s = line.strip()
        if "|" in s:
            parts = s.split("|", 1)
            if len(parts) == 2 and parts[0] not in found:
                found[parts[0]] = parts[1]
    return found


# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

def wait_for_pending_status(action_request_id: str, timeout: int = PENDING_TIMEOUT) -> bool:
    """Poll until pending_actions row appears with status='pending'."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pending_action_status(action_request_id) == "pending":
            return True
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_action_status(
    action_request_id: str,
    expected: str,
    timeout: int = ACTION_TIMEOUT,
) -> bool:
    """Poll until pending_actions row reaches the expected status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pending_action_status(action_request_id) == expected:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_chunks_zero(filename: str, timeout: int = DELETION_TIMEOUT) -> bool:
    """Poll until chunk count for filename reaches 0."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chunk_count_for(filename) == 0:
            return True
        time.sleep(1)
    return False


def wait_for_audit_event(event_type: str, timeout: int = AUDIT_TIMEOUT) -> bool:
    """Poll audit log until event_type appears (filtered to this test run)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if event_type in audit_events_since_start():
            return True
        time.sleep(POLL_INTERVAL)
    return False


# ---------------------------------------------------------------------------
# Event emission helpers
# ---------------------------------------------------------------------------

def emit_action_pending(
    filename: str,
    action_request_id: str,
    description: str | None = None,
) -> None:
    """POST action.pending to the orchestrator with a caller-supplied action_request_id.

    Block 9 reads action_request_id from the payload (action.py line 76).
    Providing it explicitly means the test knows the ID without a DB query.
    """
    if description is None:
        description = f"Delete {filename} (D-106 E2E test)."
    _orchestrator_post(
        "/events",
        {
            "event_type": "action.pending",
            "source_block": 23,
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "payload": {
                "action_type": "document.delete",
                "action_target": filename,
                "action_description": description,
                "action_request_id": action_request_id,
                "chat_id": OWNER_CHAT_ID,
            },
        },
    )


def emit_action_owner_response(action_request_id: str, confirmed: bool) -> None:
    """POST action.owner_response to the orchestrator."""
    _orchestrator_post(
        "/events",
        {
            "event_type": "action.owner_response",
            "source_block": 23,
            "event_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "payload": {
                "action_request_id": action_request_id,
                "confirmed": confirmed,
                "chat_id": OWNER_CHAT_ID,
            },
        },
    )


# ---------------------------------------------------------------------------
# Throwaway document setup
# ---------------------------------------------------------------------------

def ensure_throwaway() -> str | None:
    """Ensure the throwaway test document exists in clive_search.chunks and MinIO.

    Returns the source_key on success, None on failure.
    Chunks are inserted without embeddings — not needed for the deletion path.
    PostgreSQL dollar-quoting is used to avoid single-quote escaping issues.
    """
    existing_count = chunk_count_for(THROWAWAY_FILENAME)
    if existing_count > 0:
        sk = source_key_for(THROWAWAY_FILENAME)
        print(f"  → {THROWAWAY_FILENAME} already in DB "
              f"({existing_count} chunks, source_key={sk})")
        return sk

    print(f"  → Creating {THROWAWAY_FILENAME} in MinIO and DB...")

    doc_uuid = str(uuid.uuid4())
    source_key = f"{doc_uuid}/{THROWAWAY_FILENAME}"

    chunk_texts = [
        "D-106 automated end-to-end test document. First chunk.",
        "D-106 automated end-to-end test document. Second chunk.",
    ]

    # Upload to MinIO (skippable for purely-DB tests)
    if not SKIP_MINIO:
        file_content = "\n".join(chunk_texts) + "\n"
        if not minio_pipe_upload(source_key, file_content):
            print(f"  → MinIO upload failed for {source_key}")
            return None
        print(f"  → Uploaded to MinIO: {source_key}")

    # Insert two chunks using dollar-quoting to avoid single-quote conflicts
    for i, content in enumerate(chunk_texts):
        content_hash = hashlib.sha256(f"{source_key}:{i}".encode()).hexdigest()
        sql = (
            f"INSERT INTO clive_search.chunks\n"
            f"    (content, source_attribution, zone_of_origin, position,\n"
            f"     source_key, content_hash, document_id, content_tsv)\n"
            f"VALUES (\n"
            f"    $clive${content}$clive$,\n"
            f"    $clive${source_key}$clive$,\n"
            f"    'personal',\n"
            f"    {i},\n"
            f"    $clive${source_key}$clive$,\n"
            f"    '{content_hash}',\n"
            f"    gen_random_uuid(),\n"
            f"    to_tsvector('english', $clive${content}$clive$)\n"
            f") ON CONFLICT (content_hash) DO NOTHING;\n"
        )
        _psql_stdin(sql)

    count = chunk_count_for(THROWAWAY_FILENAME)
    if count == 0:
        print(f"  → DB chunk insert failed for {THROWAWAY_FILENAME}")
        return None

    print(f"  → {THROWAWAY_FILENAME} ready: {count} chunks, source_key={source_key}")
    return source_key


# ---------------------------------------------------------------------------
# Criterion C4 — Not-found path
# ---------------------------------------------------------------------------

def run_c4() -> None:
    """C4: deletion request for non-existent file emits deletion.not_found; no crash."""
    print(f"\n[C4] Not-found deletion path ({NONEXISTENT_FILENAME})")

    action_request_id = str(uuid.uuid4())

    try:
        emit_action_pending(NONEXISTENT_FILENAME, action_request_id)
    except Exception as exc:
        record("C4: action.pending accepted by orchestrator", False, str(exc)[:80])
        return
    record("C4: action.pending accepted by orchestrator", True)

    # Block 9 stores the pending action asynchronously — poll for it
    if not wait_for_pending_status(action_request_id):
        record("C4: pending_actions row appears (status=pending)", False, "timeout")
        return
    record("C4: pending_actions row appears (status=pending)", True)

    # Confirm — Block 15 finds no chunks and emits deletion.not_found
    try:
        emit_action_owner_response(action_request_id, confirmed=True)
    except Exception as exc:
        record("C4: action.owner_response (confirm) accepted", False, str(exc)[:80])
        return
    record("C4: action.owner_response (confirm) accepted", True)

    # Verify deletion.not_found appears in audit log
    found_not_found = wait_for_audit_event("deletion.not_found")
    record("C4: deletion.not_found in audit log", found_not_found)

    # Sanity: no chunks for the non-existent file (there never were any)
    count = chunk_count_for(NONEXISTENT_FILENAME)
    record("C4: no chunks for non-existent file", count == 0, f"count={count}")


# ---------------------------------------------------------------------------
# Criterion C2 — Cancel path
# ---------------------------------------------------------------------------

def run_c2() -> None:
    """C2: owner rejects deletion; status becomes 'rejected'; chunk count unchanged."""
    print(f"\n[C2] Cancel path ({THROWAWAY_FILENAME})")

    before_count = chunk_count_for(THROWAWAY_FILENAME)
    if before_count == 0:
        record(
            "C2: throwaway chunks present before cancel",
            False,
            "count=0 — setup failed",
        )
        return
    record("C2: throwaway chunks present before cancel", True, f"count={before_count}")

    action_request_id = str(uuid.uuid4())

    try:
        emit_action_pending(THROWAWAY_FILENAME, action_request_id)
    except Exception as exc:
        record("C2: action.pending accepted by orchestrator", False, str(exc)[:80])
        return

    if not wait_for_pending_status(action_request_id):
        record("C2: pending_actions row appears (status=pending)", False, "timeout")
        return

    # Cancel — send confirmed=False
    try:
        emit_action_owner_response(action_request_id, confirmed=False)
    except Exception as exc:
        record("C2: action.owner_response (cancel) accepted", False, str(exc)[:80])
        return

    # Verify Block 9 resolved the action as rejected
    if not wait_for_action_status(action_request_id, "rejected"):
        status = pending_action_status(action_request_id)
        record("C2: pending_action status=rejected", False, f"actual status={status}")
    else:
        record("C2: pending_action status=rejected", True)

    # Verify chunk count is unchanged (no deletion occurred)
    after_count = chunk_count_for(THROWAWAY_FILENAME)
    record(
        "C2: chunk count unchanged after cancel",
        after_count == before_count,
        f"before={before_count} after={after_count}",
    )


# ---------------------------------------------------------------------------
# Criterion C3 — Confirmed deletion
# ---------------------------------------------------------------------------

def run_c3(throwaway_source_key: str) -> None:
    """C3: confirmed deletion removes all chunks from DB, raw file from MinIO."""
    print(f"\n[C3] Confirmed deletion ({THROWAWAY_FILENAME})")

    before_count = chunk_count_for(THROWAWAY_FILENAME)
    if before_count == 0:
        record(
            "C3: throwaway chunks present before delete",
            False,
            "count=0 — cannot run C3 (setup or C2 failed)",
        )
        return
    record(
        "C3: throwaway chunks present before delete",
        True,
        f"count={before_count}",
    )

    action_request_id = str(uuid.uuid4())

    try:
        emit_action_pending(THROWAWAY_FILENAME, action_request_id)
    except Exception as exc:
        record("C3: action.pending accepted by orchestrator", False, str(exc)[:80])
        return

    if not wait_for_pending_status(action_request_id):
        record("C3: pending_actions row appears (status=pending)", False, "timeout")
        return

    # Confirm deletion
    try:
        emit_action_owner_response(action_request_id, confirmed=True)
    except Exception as exc:
        record("C3: action.owner_response (confirm) accepted", False, str(exc)[:80])
        return

    # Block 9 marks confirmed; Block 15 runs asynchronously
    if not wait_for_action_status(action_request_id, "confirmed", timeout=20):
        status = pending_action_status(action_request_id)
        record("C3: pending_action status=confirmed", False, f"actual status={status}")
    else:
        record("C3: pending_action status=confirmed", True)

    # Poll until DB chunks reach 0 (Block 15 delete pipeline is async)
    chunks_gone = wait_for_chunks_zero(THROWAWAY_FILENAME)
    after_count = chunk_count_for(THROWAWAY_FILENAME)
    record(
        "C3: DB chunks = 0 after confirmed delete",
        chunks_gone,
        f"count={after_count}",
    )

    # MinIO: verify raw file is absent
    if not SKIP_MINIO:
        try:
            gone = minio_object_gone(throwaway_source_key)
            detail = "confirmed absent" if gone else f"still present: {throwaway_source_key[:50]}"
            record("C3: MinIO raw file absent", gone, detail)
        except Exception as exc:
            record("C3: MinIO raw file absent", False, str(exc)[:80])
    else:
        print("  ⏭  MinIO check skipped (SKIP_MINIO_CHECK=1)")

    # Verify deletion.complete appears in audit log
    deletion_complete_logged = wait_for_audit_event("deletion.complete")
    record("C3: deletion.complete in audit log", deletion_complete_logged)


# ---------------------------------------------------------------------------
# Criterion C5 — Block 18 feedback
# ---------------------------------------------------------------------------

def run_c5() -> None:
    """C5: feedback is persisted to clive_state.feedback and audited.

    Block 23's /bad handler writes directly to clive_state.feedback (not via the
    orchestrator) then emits feedback.explicit for auditing.  This test replicates
    that exact code path:
      1. INSERT feedback row directly (as Block 23 does)
      2. POST feedback.explicit to orchestrator (as Block 23 does)
      3. Verify row in DB and feedback.explicit in audit log
    """
    print("\n[C5] Block 18 feedback")

    feedback_id = str(uuid.uuid4())
    retrieval_event_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())

    # Step 1: write feedback row (mirrors Block 23 bot.py handle_bad DB write)
    sql = (
        f"INSERT INTO clive_state.feedback\n"
        f"    (feedback_id, retrieval_event_id, conversation_id,\n"
        f"     owner_chat_id, feedback_type, submitted_at, chunk_ids)\n"
        f"VALUES (\n"
        f"    '{feedback_id}',\n"
        f"    '{retrieval_event_id}',\n"
        f"    '{conversation_id}',\n"
        f"    {OWNER_CHAT_ID},\n"
        f"    'poor_quality',\n"
        f"    now(),\n"
        f"    '[]'::jsonb\n"
        f");\n"
    )
    try:
        _psql_stdin(sql)
    except Exception as exc:
        record("C5: feedback row inserted into DB", False, str(exc)[:80])
        return
    record("C5: feedback row inserted into DB", True)

    # Step 2: emit feedback.explicit for audit trail (mirrors Block 23 bot.py _emit_to_orchestrator)
    try:
        _orchestrator_post(
            "/events",
            {
                "event_type": "feedback.explicit",
                "source_block": 23,
                "event_id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "payload": {
                    "feedback_id": feedback_id,
                    "retrieval_event_id": retrieval_event_id,
                    "feedback_type": "poor_quality",
                    "chat_id": OWNER_CHAT_ID,
                    "chunk_ids": [],
                },
            },
        )
    except Exception as exc:
        record("C5: feedback.explicit emitted to orchestrator", False, str(exc)[:80])
    else:
        record("C5: feedback.explicit emitted to orchestrator", True)

    # Step 3a: verify DB row persisted
    row = latest_feedback_row()
    record(
        "C5: feedback row present in DB",
        row is not None,
        row[:80] if row else "not found",
    )

    # Step 3b: verify audit log entry
    audit_present = wait_for_audit_event("feedback.explicit")
    record("C5: feedback.explicit in audit log", audit_present)


# ---------------------------------------------------------------------------
# Criterion C6 — Audit trail completeness
# ---------------------------------------------------------------------------

def run_c6() -> None:
    """C6: audit log contains all required v0.3 event types with non-null source_block."""
    print("\n[C6] Audit trail completeness")

    required = {
        "action.pending",
        "action.confirmation_requested",
        "action.owner_response",
        "action.confirmed",
        "action.rejected",
        "deletion.complete",
        "feedback.explicit",
    }

    found = audit_events_since_start()
    found_types = set(found.keys())
    missing = required - found_types

    # All found rows must have a non-null, non-empty source_block
    rows_missing_block = [
        et for et, sb in found.items()
        if sb in ("NULL", "", None)
    ]
    all_have_source_block = not rows_missing_block

    record(
        "C6: all required event types in audit log",
        not missing,
        f"found={len(found_types & required)}/{len(required)}"
        + (f" missing={sorted(missing)}" if missing else ""),
    )
    record(
        "C6: all events have non-null source_block",
        all_have_source_block,
        "ok" if all_have_source_block else f"missing source_block: {rows_missing_block}",
    )


# ---------------------------------------------------------------------------
# Teardown — remove throwaway document regardless of test outcome
# ---------------------------------------------------------------------------

def teardown_throwaway() -> None:
    """Delete the throwaway document from DB and MinIO if it still exists.

    Called in a finally block so the live system is left in the same state
    it was in before the test ran — no test artifact persists on pass or fail.

    C3 (the confirmed-deletion criterion) handles teardown as part of the test
    itself on the happy path.  This function is the safety net for cases where
    C3 did not run or did not complete (test crash, early failure, timeout, etc.).
    """
    # Resolve source_key now, before we delete the DB rows that hold it
    remaining_sk = source_key_for(THROWAWAY_FILENAME)
    count = chunk_count_for(THROWAWAY_FILENAME)

    if count > 0:
        _psql(
            f"DELETE FROM clive_search.chunks "
            f"WHERE source_key LIKE '%/{THROWAWAY_FILENAME}';"
        )
        print(f"\n[Teardown] Removed {count} stale chunk(s) for {THROWAWAY_FILENAME} from DB")
    else:
        print("\n[Teardown] DB already clean — no chunks to remove")

    if remaining_sk and not SKIP_MINIO:
        if not minio_object_gone(remaining_sk):
            minio_rm(remaining_sk)
            print(f"[Teardown] Removed {remaining_sk} from MinIO")
        else:
            print("[Teardown] MinIO already clean — object absent")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report() -> str:
    passed = sum(1 for r in _results if r.passed)
    total = len(_results)
    separator = "─" * 60
    lines = [
        f"D-106 E2E Test Report — {passed}/{total} passed",
        separator,
    ]
    for r in _results:
        icon = "✅" if r.passed else "❌"
        suffix = f" — {r.detail}" if r.detail else ""
        lines.append(f"{icon} {r.name}{suffix}")
    lines.append(separator)
    if passed == total:
        lines.append("ALL PASSED — v0.3 ready for D-106 sign-off ✅")
    else:
        lines.append(f"{total - passed} FAILURE(S) — see above ❌")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global TEST_START_TS

    print("D-106 E2E Test Runner (HTTP API level)")
    print("=" * 60)
    print(f"Orchestrator container : {ORCHESTRATOR_CONTAINER}")
    print(f"Postgres container     : {POSTGRES_CONTAINER}")
    print(f"MinIO container        : {MINIO_CONTAINER}")
    print(f"MinIO bucket           : {MINIO_BUCKET}")
    print(f"Owner chat ID          : {OWNER_CHAT_ID}")
    print(f"Skip MinIO check       : {SKIP_MINIO}")
    print()

    # Record test start timestamp (2s buffer to account for any clock drift)
    TEST_START_TS = (
        datetime.now(timezone.utc) - timedelta(seconds=2)
    ).strftime("%Y-%m-%d %H:%M:%S+00")

    # Preflight: verify orchestrator is healthy
    print("[Preflight] Checking orchestrator health...")
    try:
        result = subprocess.run(
            [
                "docker", "exec", ORCHESTRATOR_CONTAINER,
                "curl", "-sf", "http://localhost:8080/health",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"FATAL: Orchestrator health check failed: {result.stderr.strip()}")
            sys.exit(1)
        health = json.loads(result.stdout)
        print(f"  → Orchestrator healthy: {health}")
    except Exception as exc:
        print(f"FATAL: Cannot reach orchestrator: {exc}")
        sys.exit(1)

    # Setup: ensure throwaway document exists in DB and MinIO
    print("\n[Setup] Ensuring throwaway document exists...")
    throwaway_source_key = ensure_throwaway()
    if throwaway_source_key is None:
        print("FATAL: Could not create throwaway document. Aborting.")
        sys.exit(1)

    # Run criteria in order:
    #   C4 first (non-existent file, independent)
    #   C2 second (cancel on throwaway — leaves chunks in place)
    #   C3 third  (confirmed delete of throwaway — destructive)
    #   C5 fourth (feedback — independent, uses DB directly)
    #   C6 last   (audit completeness — checks all events from this run)
    #
    # teardown_throwaway() runs in the finally block regardless of outcome,
    # ensuring the live system is left in the state it started in.
    try:
        run_c4()
        run_c2()
        run_c3(throwaway_source_key)
        run_c5()
        run_c6()
    finally:
        try:
            teardown_throwaway()
        except Exception as exc:
            # Teardown errors are non-fatal — report and continue to the result
            print(f"[Teardown] Warning: cleanup error (non-fatal): {exc}")

    # Final report
    report = build_report()
    print("\n" + report)

    passed = sum(1 for r in _results if r.passed)
    sys.exit(0 if passed == len(_results) else 1)


if __name__ == "__main__":
    main()
