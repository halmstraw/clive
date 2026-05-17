"""Extended tests for scheduler.py — covering uncovered paths."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import orchestrator.scheduler as scheduler_mod


def _make_mock_pool(conn: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool


# ---------------------------------------------------------------------------
# _load_dispatch (lines 194-206)
# ---------------------------------------------------------------------------

class TestLoadDispatch:
    def test_loads_known_workers(self):
        """_load_dispatch should populate _WORKERS with daily_digest and knowledge_maintenance."""
        scheduler_mod._WORKERS.clear()
        scheduler_mod._load_dispatch()
        # Both modules exist; both should load
        assert "daily_digest" in scheduler_mod._WORKERS
        assert "knowledge_maintenance" in scheduler_mod._WORKERS



# ---------------------------------------------------------------------------
# _load_worker_configs
# ---------------------------------------------------------------------------

class TestLoadWorkerConfigs:
    @pytest.mark.asyncio
    async def test_returns_worker_list(self):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"worker_name": "daily_digest", "cron_expression": "0 8 * * *", "execution_scope": ["write:telegram"]},
        ])

        pool = _make_mock_pool(mock_conn)
        original = scheduler_mod._pool
        try:
            scheduler_mod._pool = pool
            configs = await scheduler_mod._load_worker_configs()
        finally:
            scheduler_mod._pool = original

        assert len(configs) == 1
        assert configs[0]["worker_name"] == "daily_digest"


# ---------------------------------------------------------------------------
# _run_worker — success and failure paths
# ---------------------------------------------------------------------------

class TestRunWorker:
    @pytest.mark.asyncio
    async def test_run_worker_success(self):
        run_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=run_id)
        mock_conn.execute = AsyncMock()
        pool = _make_mock_pool(mock_conn)

        mock_worker = AsyncMock(return_value="success_summary")

        config = {
            "worker_name": "daily_digest",
            "cron_expression": "0 8 * * *",
            "execution_scope": ["write:telegram"],
        }

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        try:
            scheduler_mod._pool = pool
            scheduler_mod._WORKERS["daily_digest"] = mock_worker
            await scheduler_mod._run_worker(config)
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)

        mock_worker.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_worker_not_in_dispatch_skips(self):
        """Worker not in _WORKERS is logged and skipped."""
        config = {
            "worker_name": "nonexistent_worker",
            "cron_expression": "0 8 * * *",
            "execution_scope": [],
        }

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        try:
            scheduler_mod._pool = MagicMock()
            scheduler_mod._WORKERS.pop("nonexistent_worker", None)
            # Should not raise
            await scheduler_mod._run_worker(config)
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)

    @pytest.mark.asyncio
    async def test_run_worker_exception_does_not_propagate(self):
        """Worker exception is caught; scheduler must stay alive (D-025)."""
        run_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=run_id)
        mock_conn.execute = AsyncMock()
        pool = _make_mock_pool(mock_conn)

        failing_worker = AsyncMock(side_effect=Exception("worker crash"))

        config = {
            "worker_name": "daily_digest",
            "cron_expression": "0 8 * * *",
            "execution_scope": [],
        }

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        try:
            scheduler_mod._pool = pool
            scheduler_mod._WORKERS["daily_digest"] = failing_worker
            # Should not raise — exception is caught
            await scheduler_mod._run_worker(config)
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)

    @pytest.mark.asyncio
    async def test_run_worker_error_status_update_failure_does_not_propagate(self):
        """When both the worker and the error-status DB update fail, scheduler still stays alive."""
        run_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=run_id)
        # execute raises — simulates the error-status UPDATE failing
        mock_conn.execute = AsyncMock(side_effect=Exception("db update error"))
        pool = _make_mock_pool(mock_conn)

        failing_worker = AsyncMock(side_effect=Exception("worker crash"))

        config = {
            "worker_name": "daily_digest",
            "cron_expression": "0 8 * * *",
            "execution_scope": [],
        }

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        try:
            scheduler_mod._pool = pool
            scheduler_mod._WORKERS["daily_digest"] = failing_worker
            # Should not raise — inner exception is caught at lines 310-311
            await scheduler_mod._run_worker(config)
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)


# ---------------------------------------------------------------------------
# scheduler_loop — startup and CancelledError paths
# ---------------------------------------------------------------------------

class TestSchedulerLoop:
    @pytest.mark.asyncio
    async def test_scheduler_loop_exits_cleanly_on_cancelled_error(self):
        """scheduler_loop returns (no re-raise) on CancelledError from sleep."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])  # No workers
        pool = _make_mock_pool(mock_conn)

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        scheduler_mod._load_dispatch()

        try:
            scheduler_mod._pool = pool
            with patch("orchestrator.scheduler.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError())):
                await scheduler_mod.scheduler_loop()  # Should return without raising
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)

    @pytest.mark.asyncio
    async def test_scheduler_loop_runs_iteration_then_exits(self):
        """Loop iterates (checking workers) before being cancelled on second sleep."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "worker_name": "daily_digest",
                "cron_expression": "0 8 * * *",  # 8am daily — next_run will be in the future
                "execution_scope": ["write:telegram"],
            }
        ])
        pool = _make_mock_pool(mock_conn)

        sleep_count = 0

        async def counting_sleep(secs):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()
            # First sleep: returns normally so the loop iterates

        original = scheduler_mod._pool
        original_workers = dict(scheduler_mod._WORKERS)
        scheduler_mod._load_dispatch()

        try:
            scheduler_mod._pool = pool
            with patch("orchestrator.scheduler.asyncio.sleep", counting_sleep):
                await scheduler_mod.scheduler_loop()
        finally:
            scheduler_mod._pool = original
            scheduler_mod._WORKERS.clear()
            scheduler_mod._WORKERS.update(original_workers)

        # sleep was called twice — startup loop + one iteration
        assert sleep_count == 2
