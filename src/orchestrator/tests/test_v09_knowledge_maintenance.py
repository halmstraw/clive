"""v0.9 Block 10 — Unit tests for the knowledge_maintenance worker.

Criteria covered (DONE WHEN from task spec):
  run(): returns "No stale chunks found" when query returns empty results
  run(): calls request_confirmation when stale chunks are found (3 chunks)
  run(): SQL includes LIMIT 5 — confirms batch cap enforced at query layer
  handle_prune_confirmed(): executes DELETE with correct chunk_ids
  handle_prune_confirmed(): calls _push_prune_complete with correct count
  handle_prune_confirmed(): returns early on empty chunk list
  handle_prune_confirmed(): returns early on invalid JSON action_target

D-006: run() NEVER deletes chunks; only presents confirmation request.
       If scoped_push lacks 'request_confirmation', logs WARN and returns.
D-003: _push_prune_complete uses HTTP to Block 23 /alert; no Telegram import.
"""

from __future__ import annotations

import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.events.schema import CLIVEEvent
from orchestrator.workers.knowledge_maintenance import (
    handle_prune_confirmed,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pool(fetch_return=None, execute_return=None):
    """Create a minimal asyncpg pool mock.

    fetch_return  — list returned by conn.fetch (stale chunk rows)
    execute_return — value returned by conn.execute (DELETE result)
    """
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=execute_return)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


def _make_stale_row(
    chunk_id: uuid.UUID | None = None,
    source: str = "test_doc.txt",
    days_old: int = 100,
) -> dict:
    """Return a dict mimicking an asyncpg Record row for a stale chunk.

    asyncpg Records support dict-style access; plain dicts work as drop-ins
    in unit tests because the worker code only uses row["key"] notation.
    """
    if chunk_id is None:
        chunk_id = uuid.uuid4()
    created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
    return {
        "chunk_id": chunk_id,
        "source_attribution": source,
        "created_at": created_at,
    }


def _make_confirmed_event(chunk_ids: list[str]) -> CLIVEEvent:
    """Build an action.confirmed CLIVEEvent with a knowledge.prune action_target."""
    chunks = [
        {"chunk_id": cid, "source": "doc.txt", "days_old": 95}
        for cid in chunk_ids
    ]
    return CLIVEEvent(
        event_type="action.confirmed",
        source_block=13,
        conversation_id=None,
        payload={
            "action_type": "knowledge.prune",
            "action_target": json.dumps(chunks),
        },
    )


# ---------------------------------------------------------------------------
# run() — no stale chunks
# ---------------------------------------------------------------------------

class TestRunNoStaleChunks:

    @pytest.mark.asyncio
    async def test_returns_no_stale_message_when_empty(self):
        """run() returns 'No stale chunks found' when query returns no rows."""
        pool, _ = _make_mock_pool(fetch_return=[])
        scoped_push = {"request_confirmation": AsyncMock()}

        result = await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        assert "No stale chunks found" in result

    @pytest.mark.asyncio
    async def test_does_not_call_request_confirmation_when_empty(self):
        """run() must NOT call request_confirmation when no stale chunks exist."""
        pool, _ = _make_mock_pool(fetch_return=[])
        mock_confirm = AsyncMock()
        scoped_push = {"request_confirmation": mock_confirm}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        mock_confirm.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_stale_message_includes_threshold_days(self):
        """'No stale chunks found' message includes the configured threshold value."""
        pool, _ = _make_mock_pool(fetch_return=[])
        scoped_push = {}

        with patch.dict("os.environ", {"KNOWLEDGE_MAINTENANCE_THRESHOLD_DAYS": "60"}):
            result = await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        assert "60" in result


# ---------------------------------------------------------------------------
# run() — stale chunks found
# ---------------------------------------------------------------------------

class TestRunStaleChunksFound:

    @pytest.mark.asyncio
    async def test_calls_request_confirmation_when_chunks_found(self):
        """run() calls request_confirmation when 3 stale chunks are returned."""
        rows = [
            _make_stale_row(source="doc_a.txt", days_old=100),
            _make_stale_row(source="doc_b.txt", days_old=120),
            _make_stale_row(source="doc_c.txt", days_old=150),
        ]
        pool, _ = _make_mock_pool(fetch_return=rows)
        mock_confirm = AsyncMock()
        scoped_push = {"request_confirmation": mock_confirm}

        with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "99001"}):
            await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        mock_confirm.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_confirmation_uses_knowledge_prune_action_type(self):
        """action_type passed to request_confirmation is 'knowledge.prune'."""
        rows = [_make_stale_row()]
        pool, _ = _make_mock_pool(fetch_return=rows)
        mock_confirm = AsyncMock()
        scoped_push = {"request_confirmation": mock_confirm}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        call_kwargs = mock_confirm.call_args.kwargs
        assert call_kwargs["action_type"] == "knowledge.prune"

    @pytest.mark.asyncio
    async def test_action_target_contains_all_chunk_ids(self):
        """action_target JSON contains chunk_id for each stale row found."""
        cids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        rows = [_make_stale_row(chunk_id=cid) for cid in cids]
        pool, _ = _make_mock_pool(fetch_return=rows)
        mock_confirm = AsyncMock()
        scoped_push = {"request_confirmation": mock_confirm}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        call_kwargs = mock_confirm.call_args.kwargs
        chunk_list = json.loads(call_kwargs["action_target"])
        returned_ids = {c["chunk_id"] for c in chunk_list}
        expected_ids = {str(cid) for cid in cids}
        assert returned_ids == expected_ids

    @pytest.mark.asyncio
    async def test_chat_id_set_from_env(self):
        """chat_id in request_confirmation call matches TELEGRAM_OWNER_CHAT_ID env var."""
        rows = [_make_stale_row()]
        pool, _ = _make_mock_pool(fetch_return=rows)
        mock_confirm = AsyncMock()
        scoped_push = {"request_confirmation": mock_confirm}

        with patch.dict("os.environ", {"TELEGRAM_OWNER_CHAT_ID": "42000"}):
            await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        call_kwargs = mock_confirm.call_args.kwargs
        assert call_kwargs["chat_id"] == 42000

    @pytest.mark.asyncio
    async def test_return_value_includes_chunk_count(self):
        """run() return value includes the number of chunks flagged."""
        rows = [_make_stale_row(), _make_stale_row(), _make_stale_row()]
        pool, _ = _make_mock_pool(fetch_return=rows)
        scoped_push = {"request_confirmation": AsyncMock()}

        result = await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        assert "3" in result
        assert "Flagged" in result

    @pytest.mark.asyncio
    async def test_sql_contains_limit_5(self):
        """SQL query passed to conn.fetch includes LIMIT 5 — confirms batch cap."""
        pool, conn = _make_mock_pool(fetch_return=[])
        scoped_push = {}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        conn.fetch.assert_called_once()
        sql = conn.fetch.call_args.args[0]
        assert "LIMIT 5" in sql

    @pytest.mark.asyncio
    async def test_sql_filters_retrieval_count_zero(self):
        """SQL query includes retrieval_count = 0 filter to select unaccessed chunks."""
        pool, conn = _make_mock_pool(fetch_return=[])
        scoped_push = {}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        sql = conn.fetch.call_args.args[0]
        assert "retrieval_count" in sql

    @pytest.mark.asyncio
    async def test_sql_filters_by_created_at_cutoff(self):
        """SQL query filters created_at < $1 (the computed cutoff datetime)."""
        pool, conn = _make_mock_pool(fetch_return=[])
        scoped_push = {}

        await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        sql = conn.fetch.call_args.args[0]
        assert "created_at" in sql
        # Cutoff datetime should be the second positional arg (after SQL string)
        cutoff_arg = conn.fetch.call_args.args[1]
        assert isinstance(cutoff_arg, datetime.datetime)

    @pytest.mark.asyncio
    async def test_no_confirmation_scope_logs_warn_and_does_not_delete(self):
        """D-006: run() logs a warning and returns without deleting when no confirmation scope."""
        rows = [_make_stale_row()]
        pool, conn = _make_mock_pool(fetch_return=rows)
        scoped_push = {}  # no 'request_confirmation' key — scope violation

        # Must not raise; must not call conn.execute (no deletion)
        result = await run(run_id=str(uuid.uuid4()), pool=pool, scoped_push=scoped_push)

        conn.execute.assert_not_called()
        assert "Flagged" in result  # returns outcome but did not delete


# ---------------------------------------------------------------------------
# handle_prune_confirmed() — correct deletion
# ---------------------------------------------------------------------------

class TestHandlePruneConfirmed:

    @pytest.mark.asyncio
    async def test_deletes_correct_chunk_ids(self):
        """handle_prune_confirmed() executes DELETE with the exact chunk_ids from the event."""
        cids = [str(uuid.uuid4()), str(uuid.uuid4())]
        event = _make_confirmed_event(cids)
        pool, conn = _make_mock_pool()

        with (
            patch("orchestrator.workers.knowledge_maintenance._pool", pool),
            patch(
                "orchestrator.workers.knowledge_maintenance._push_prune_complete",
                AsyncMock(),
            ),
        ):
            await handle_prune_confirmed(event)

        conn.execute.assert_called_once()
        sql = conn.execute.call_args.args[0]
        assert "DELETE" in sql
        assert "clive_search.chunks" in sql
        assert "chunk_id" in sql

        # Verify the UUID list matches the original chunk_ids
        uuid_list_arg = conn.execute.call_args.args[1]
        returned_id_strings = {str(u) for u in uuid_list_arg}
        assert returned_id_strings == set(cids)

    @pytest.mark.asyncio
    async def test_calls_push_prune_complete_with_correct_count(self):
        """handle_prune_confirmed() calls _push_prune_complete with the chunk count."""
        cids = [str(uuid.uuid4()) for _ in range(3)]
        event = _make_confirmed_event(cids)
        pool, _ = _make_mock_pool()
        mock_push = AsyncMock()

        with (
            patch("orchestrator.workers.knowledge_maintenance._pool", pool),
            patch(
                "orchestrator.workers.knowledge_maintenance._push_prune_complete",
                mock_push,
            ),
        ):
            await handle_prune_confirmed(event)

        mock_push.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_returns_early_on_empty_chunk_list(self):
        """handle_prune_confirmed() returns early when action_target is an empty list."""
        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=13,
            conversation_id=None,
            payload={
                "action_type": "knowledge.prune",
                "action_target": "[]",
            },
        )
        pool, conn = _make_mock_pool()

        with patch("orchestrator.workers.knowledge_maintenance._pool", pool):
            await handle_prune_confirmed(event)

        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_on_invalid_json_action_target(self):
        """handle_prune_confirmed() returns early when action_target is not valid JSON."""
        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=13,
            conversation_id=None,
            payload={
                "action_type": "knowledge.prune",
                "action_target": "not-valid-json{{{{",
            },
        )
        pool, conn = _make_mock_pool()

        with patch("orchestrator.workers.knowledge_maintenance._pool", pool):
            await handle_prune_confirmed(event)

        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_action_target_missing(self):
        """handle_prune_confirmed() returns early when action_target key is absent."""
        event = CLIVEEvent(
            event_type="action.confirmed",
            source_block=13,
            conversation_id=None,
            payload={"action_type": "knowledge.prune"},
        )
        pool, conn = _make_mock_pool()

        with patch("orchestrator.workers.knowledge_maintenance._pool", pool):
            await handle_prune_confirmed(event)

        # Empty default '[]' → no chunk_ids → early return without DELETE
        conn.execute.assert_not_called()
