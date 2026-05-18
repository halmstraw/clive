"""v0.9 Block 10 — Unit tests for the worker scheduler.

Criteria covered (DONE WHEN from task spec):
  _load_worker_configs: returns only enabled cron workers (SQL filter verified)
  _run_worker: inserts worker_runs row with status='running' then 'success'
  _run_worker: sets status='error' on exception without re-raising
  make_scoped_push: returns 'notify' when write:telegram in execution_scope
  make_scoped_push: does NOT return 'notify' when write:telegram absent

D-003: workers push to Block 23 via HTTP through scheduler push helpers.
D-006: _push_worker_confirmation is the confirmation gate.
D-025: worker_runs rows are idempotent on run_id (UUID PRIMARY KEY).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.scheduler import (
    _load_worker_configs,
    _run_worker,
    _WORKERS,
    make_scoped_push,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pool(fetchval_return=None, fetch_return=None, execute_return=None):
    """Create a mock asyncpg pool with configurable return values.

    fetchval_return  — returned by conn.fetchval (INSERT RETURNING run_id)
    fetch_return     — returned by conn.fetch (_load_worker_configs)
    execute_return   — returned by conn.execute (UPDATE worker_runs)
    """
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=execute_return)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


def _worker_config(
    worker_name: str = "daily_digest",
    cron_expression: str = "0 8 * * *",
    execution_scope: list[str] | None = None,
) -> dict:
    return {
        "worker_name": worker_name,
        "cron_expression": cron_expression,
        "execution_scope": execution_scope or ["write:telegram"],
    }


# ---------------------------------------------------------------------------
# make_scoped_push tests
# ---------------------------------------------------------------------------

class TestMakeScopedPush:

    def test_notify_present_when_telegram_in_scope(self):
        """make_scoped_push returns 'notify' callable when write:telegram in scope."""
        scope = ["write:telegram"]
        result = make_scoped_push(scope)
        assert "notify" in result
        assert callable(result["notify"])

    def test_notify_absent_when_telegram_not_in_scope(self):
        """make_scoped_push does NOT return 'notify' when write:telegram absent."""
        scope = ["read:queries", "write:confirmations"]
        result = make_scoped_push(scope)
        assert "notify" not in result

    def test_request_confirmation_present_when_confirmations_in_scope(self):
        """make_scoped_push returns 'request_confirmation' when write:confirmations in scope."""
        scope = ["write:confirmations"]
        result = make_scoped_push(scope)
        assert "request_confirmation" in result
        assert callable(result["request_confirmation"])

    def test_request_confirmation_absent_when_confirmations_not_in_scope(self):
        """make_scoped_push does NOT return 'request_confirmation' when absent from scope."""
        scope = ["write:telegram", "read:queries"]
        result = make_scoped_push(scope)
        assert "request_confirmation" not in result

    def test_empty_scope_returns_empty_dict(self):
        """make_scoped_push with empty scope returns an empty dict."""
        result = make_scoped_push([])
        assert result == {}

    def test_full_scope_returns_both_capabilities(self):
        """make_scoped_push with both write scopes returns both capabilities."""
        scope = ["write:telegram", "write:confirmations"]
        result = make_scoped_push(scope)
        assert "notify" in result
        assert "request_confirmation" in result


# ---------------------------------------------------------------------------
# _load_worker_configs tests
# ---------------------------------------------------------------------------

class TestLoadWorkerConfigs:

    @pytest.mark.asyncio
    async def test_returns_enabled_cron_workers(self):
        """_load_worker_configs returns workers from DB as list of dicts."""
        expected_rows = [
            {
                "worker_name": "daily_digest",
                "cron_expression": "0 8 * * *",
                "execution_scope": ["write:telegram"],
            },
            {
                "worker_name": "knowledge_maintenance",
                "cron_expression": "0 9 * * 1",
                "execution_scope": ["read:storage", "write:confirmations"],
            },
        ]
        pool, conn = _make_mock_pool(fetch_return=expected_rows)

        with patch("orchestrator.scheduler._pool", pool):
            result = await _load_worker_configs()

        assert len(result) == 2
        assert result[0]["worker_name"] == "daily_digest"
        assert result[1]["worker_name"] == "knowledge_maintenance"

    @pytest.mark.asyncio
    async def test_sql_filters_enabled_and_cron(self):
        """_load_worker_configs SQL must filter for schedule_type='cron' and enabled=TRUE."""
        pool, conn = _make_mock_pool(fetch_return=[])

        with patch("orchestrator.scheduler._pool", pool):
            await _load_worker_configs()

        conn.fetch.assert_called_once()
        sql = conn.fetch.call_args.args[0]
        assert "schedule_type" in sql
        assert "cron" in sql
        assert "enabled" in sql

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_workers(self):
        """_load_worker_configs returns empty list when DB returns no rows."""
        pool, _ = _make_mock_pool(fetch_return=[])

        with patch("orchestrator.scheduler._pool", pool):
            result = await _load_worker_configs()

        assert result == []

    @pytest.mark.asyncio
    async def test_joins_tool_registry(self):
        """_load_worker_configs SQL must join tool_registry to check enabled flag."""
        pool, conn = _make_mock_pool(fetch_return=[])

        with patch("orchestrator.scheduler._pool", pool):
            await _load_worker_configs()

        sql = conn.fetch.call_args.args[0]
        assert "tool_registry" in sql


# ---------------------------------------------------------------------------
# _run_worker tests
# ---------------------------------------------------------------------------

class TestRunWorker:

    @pytest.mark.asyncio
    async def test_inserts_running_then_updates_success(self):
        """_run_worker inserts worker_runs with status='running' then 'success'."""
        run_id = uuid.uuid4()
        pool, conn = _make_mock_pool(fetchval_return=run_id)

        mock_worker = AsyncMock(return_value="processed 10 items")
        config = _worker_config(worker_name="daily_digest", execution_scope=["write:telegram"])

        with (
            patch("orchestrator.scheduler._pool", pool),
            patch.dict(_WORKERS, {"daily_digest": mock_worker}),
            patch("orchestrator.scheduler.worker_runs_total") as mock_counter,
        ):
            mock_labels = MagicMock()
            mock_counter.labels.return_value = mock_labels

            await _run_worker(config)

        # First DB call: INSERT with status='running' — fetchval
        conn.fetchval.assert_called_once()
        insert_sql = conn.fetchval.call_args.args[0]
        assert "worker_runs" in insert_sql
        assert "running" in insert_sql
        assert "RETURNING run_id" in insert_sql
        assert conn.fetchval.call_args.args[1] == "daily_digest"

        # Worker was called with correct args
        mock_worker.assert_called_once_with(run_id, pool, mock_worker.call_args.args[2])

        # Second DB call: UPDATE with status='success' — execute
        conn.execute.assert_called_once()
        update_sql = conn.execute.call_args.args[0]
        assert "success" in update_sql
        assert "completed_at" in update_sql

        # Prometheus counter incremented with 'success'
        mock_counter.labels.assert_called_with(worker_name="daily_digest", status="success")
        mock_labels.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_error_status_on_exception_without_raising(self):
        """_run_worker sets status='error' on exception and does NOT re-raise."""
        run_id = uuid.uuid4()
        pool, conn = _make_mock_pool(fetchval_return=run_id)

        failing_worker = AsyncMock(side_effect=RuntimeError("db connection lost"))
        config = _worker_config(worker_name="daily_digest", execution_scope=["write:telegram"])

        with (
            patch("orchestrator.scheduler._pool", pool),
            patch.dict(_WORKERS, {"daily_digest": failing_worker}),
            patch("orchestrator.scheduler.worker_runs_total") as mock_counter,
        ):
            mock_labels = MagicMock()
            mock_counter.labels.return_value = mock_labels

            # Must NOT raise — scheduler stays alive
            await _run_worker(config)

        # UPDATE must use status='error'
        conn.execute.assert_called_once()
        update_sql = conn.execute.call_args.args[0]
        assert "error" in update_sql

        # error_detail is the exception string
        error_detail_arg = conn.execute.call_args.args[1]
        assert "db connection lost" in error_detail_arg

        # Prometheus counter incremented with 'error'
        mock_counter.labels.assert_called_with(worker_name="daily_digest", status="error")
        mock_labels.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_worker_not_in_dispatch_table(self):
        """_run_worker logs warn and returns early if worker not in _WORKERS."""
        pool, conn = _make_mock_pool()
        config = _worker_config(worker_name="unknown_worker")

        with (
            patch("orchestrator.scheduler._pool", pool),
            patch.dict(_WORKERS, {}, clear=True),
        ):
            # Must return without touching the DB at all
            await _run_worker(config)

        conn.fetchval.assert_not_called()
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_outcome_summary_set_from_worker_return_value(self):
        """outcome_summary in the UPDATE equals the string of the worker's return value."""
        run_id = uuid.uuid4()
        pool, conn = _make_mock_pool(fetchval_return=run_id)

        mock_worker = AsyncMock(return_value="sent digest to 1 user")
        config = _worker_config(worker_name="daily_digest", execution_scope=["write:telegram"])

        with (
            patch("orchestrator.scheduler._pool", pool),
            patch.dict(_WORKERS, {"daily_digest": mock_worker}),
            patch("orchestrator.scheduler.worker_runs_total") as mock_counter,
        ):
            mock_counter.labels.return_value = MagicMock()
            await _run_worker(config)

        # The first positional arg after the SQL is the outcome_summary
        update_args = conn.execute.call_args.args
        outcome_summary = update_args[1]
        assert outcome_summary == "sent digest to 1 user"

    @pytest.mark.asyncio
    async def test_none_return_value_sets_null_outcome_summary(self):
        """Worker returning None results in outcome_summary=None (NULL in DB)."""
        run_id = uuid.uuid4()
        pool, conn = _make_mock_pool(fetchval_return=run_id)

        mock_worker = AsyncMock(return_value=None)
        config = _worker_config(worker_name="daily_digest", execution_scope=["write:telegram"])

        with (
            patch("orchestrator.scheduler._pool", pool),
            patch.dict(_WORKERS, {"daily_digest": mock_worker}),
            patch("orchestrator.scheduler.worker_runs_total") as mock_counter,
        ):
            mock_counter.labels.return_value = MagicMock()
            await _run_worker(config)

        update_args = conn.execute.call_args.args
        outcome_summary = update_args[1]
        assert outcome_summary is None
