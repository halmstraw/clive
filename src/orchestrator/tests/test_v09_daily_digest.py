"""v0.9 Block 10 — Unit tests for the daily digest worker.

Criteria covered (DONE WHEN from task spec):
  run() returns non-empty outcome_summary string
  run() calls scoped_push['notify'] with message containing "Daily Digest"
  run() includes "unknown" for a field when DB query raises an exception
  run() omits feedback line when feedback_count = 0

D-003: delivery via scoped_push['notify'] — no direct Block 23 call.
D-006: daily digest is read-only; no irreversible actions.
D-025: run_id prevents duplicate processing at scheduler level.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.workers.daily_digest import run


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_pool(
    query_count: int = 5,
    action_rows: list[dict] | None = None,
    cost_usd: float = 0.0431,
    feedback_count: int = 0,
    fail_field: str | None = None,
) -> tuple[MagicMock, AsyncMock]:
    """Build a mock asyncpg pool that routes queries by SQL content.

    fail_field: if set to 'queries' | 'actions' | 'cost' | 'feedback',
                raises RuntimeError for that specific query.
    action_rows: list of dicts with keys 'action_type' and 'n'.
                 Defaults to [] (no confirmed actions).
    """
    if action_rows is None:
        action_rows = []

    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    async def fake_fetchval(sql: str, *_: object) -> int | float:
        if "conversation_turns" in sql:
            if fail_field == "queries":
                raise RuntimeError("queries DB error")
            return query_count
        if "llm_usage" in sql:
            if fail_field == "cost":
                raise RuntimeError("cost DB error")
            return cost_usd
        if "feedback" in sql:
            if fail_field == "feedback":
                raise RuntimeError("feedback DB error")
            return feedback_count
        return 0

    async def fake_fetch(sql: str, *_: object) -> list:
        if "pending_actions" in sql:
            if fail_field == "actions":
                raise RuntimeError("actions DB error")
            return action_rows
        return []

    conn.fetchval = AsyncMock(side_effect=fake_fetchval)
    conn.fetch = AsyncMock(side_effect=fake_fetch)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


def _make_scoped_push() -> tuple[dict, AsyncMock]:
    """Return (scoped_push dict, notify mock) for testing."""
    notify = AsyncMock()
    return {"notify": notify}, notify


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------

class TestDailyDigestRun:

    @pytest.mark.asyncio
    async def test_returns_non_empty_outcome_summary(self):
        """run() must return a non-empty string for worker_runs.outcome_summary."""
        pool, _ = _make_pool()
        scoped_push, _ = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_outcome_summary_contains_sent_prefix(self):
        """run() outcome_summary starts with 'Sent:' on successful delivery."""
        pool, _ = _make_pool(query_count=8)
        scoped_push, _ = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert result.startswith("Sent:")

    @pytest.mark.asyncio
    async def test_notify_called_with_daily_digest_header(self):
        """run() calls scoped_push['notify'] with a message containing 'Daily Digest'."""
        pool, _ = _make_pool()
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        notify.assert_called_once()
        message = notify.call_args.args[0]
        assert "Daily Digest" in message

    @pytest.mark.asyncio
    async def test_notify_called_once(self):
        """run() sends exactly one notification per run."""
        pool, _ = _make_pool()
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        assert notify.call_count == 1

    @pytest.mark.asyncio
    async def test_digest_contains_queries_line(self):
        """Notification message contains 'Queries:' with the correct count."""
        pool, _ = _make_pool(query_count=12)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Queries: 12" in message

    @pytest.mark.asyncio
    async def test_digest_contains_cost_line(self):
        """Notification message contains 'Cost:' formatted to 4 decimal places."""
        pool, _ = _make_pool(cost_usd=0.0431)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Cost: $0.0431" in message

    @pytest.mark.asyncio
    async def test_digest_contains_system_healthy(self):
        """Notification message always contains 'System: healthy'."""
        pool, _ = _make_pool()
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "System: healthy" in message

    @pytest.mark.asyncio
    async def test_no_actions_shows_none(self):
        """When no confirmed actions in 24h, actions field shows 'none'."""
        pool, _ = _make_pool(action_rows=[])
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Actions: none" in message

    @pytest.mark.asyncio
    async def test_actions_summary_shows_total_and_breakdown(self):
        """When confirmed actions exist, shows total with per-type breakdown."""
        action_rows = [
            {"action_type": "reminder.schedule", "n": 1},
            {"action_type": "web_search", "n": 2},
        ]
        pool, _ = _make_pool(action_rows=action_rows)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Actions: 3 (" in message
        assert "2 web_search" in message
        assert "1 reminder.schedule" in message


# ---------------------------------------------------------------------------
# Feedback line behaviour
# ---------------------------------------------------------------------------

class TestFeedbackLine:

    @pytest.mark.asyncio
    async def test_omits_feedback_line_when_count_is_zero(self):
        """run() omits the feedback line entirely when feedback_count = 0."""
        pool, _ = _make_pool(feedback_count=0)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Feedback:" not in message

    @pytest.mark.asyncio
    async def test_includes_feedback_line_when_count_is_positive(self):
        """run() includes the feedback line when feedback_count > 0."""
        pool, _ = _make_pool(feedback_count=3)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Feedback: 3 poor-quality response(s) tagged" in message

    @pytest.mark.asyncio
    async def test_includes_feedback_unknown_when_query_fails(self):
        """run() shows 'Feedback: unknown' when the feedback DB query raises."""
        pool, _ = _make_pool(fail_field="feedback")
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert "Feedback: unknown" in message


# ---------------------------------------------------------------------------
# Error handling — individual field failures are non-fatal
# ---------------------------------------------------------------------------

class TestFieldFailureGraceful:

    @pytest.mark.asyncio
    async def test_unknown_for_queries_when_db_raises(self):
        """run() includes 'unknown' for the queries field when that query raises."""
        pool, _ = _make_pool(fail_field="queries")
        scoped_push, notify = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        # Must complete without raising
        assert isinstance(result, str)
        # Notification must contain "unknown" to signal the failed field
        message = notify.call_args.args[0]
        assert "unknown" in message

    @pytest.mark.asyncio
    async def test_unknown_for_actions_when_db_raises(self):
        """run() includes 'unknown' for the actions field when that query raises."""
        pool, _ = _make_pool(fail_field="actions")
        scoped_push, notify = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert isinstance(result, str)
        message = notify.call_args.args[0]
        assert "Actions: unknown" in message

    @pytest.mark.asyncio
    async def test_unknown_for_cost_when_db_raises(self):
        """run() includes 'unknown' for the cost field when that query raises."""
        pool, _ = _make_pool(fail_field="cost")
        scoped_push, notify = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert isinstance(result, str)
        message = notify.call_args.args[0]
        assert "Cost: unknown" in message

    @pytest.mark.asyncio
    async def test_all_fields_fail_still_sends_partial_digest(self):
        """run() sends a partial digest even when all four DB queries fail."""
        pool, _ = _make_pool()

        # Override conn to always raise
        conn = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(side_effect=RuntimeError("total failure"))
        conn.fetch = AsyncMock(side_effect=RuntimeError("total failure"))
        pool.acquire = MagicMock(return_value=conn)

        scoped_push, notify = _make_scoped_push()

        # Must not raise
        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert isinstance(result, str)
        # Notification was still sent
        notify.assert_called_once()
        message = notify.call_args.args[0]
        assert "Daily Digest" in message

    @pytest.mark.asyncio
    async def test_delivery_failure_reflected_in_outcome_summary(self):
        """run() includes 'delivery_failed' in outcome_summary when notify raises."""
        pool, _ = _make_pool()
        failing_notify = AsyncMock(side_effect=Exception("network error"))
        scoped_push = {"notify": failing_notify}

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert "delivery_failed" in result

    @pytest.mark.asyncio
    async def test_no_notify_in_scope_does_not_raise(self):
        """run() handles absent 'notify' key gracefully (logs warn, returns summary)."""
        pool, _ = _make_pool()
        scoped_push = {}  # no 'notify' key

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Message format validation
# ---------------------------------------------------------------------------

class TestDigestFormat:

    @pytest.mark.asyncio
    async def test_digest_starts_with_emoji_header(self):
        """Digest first line is the emoji header with the date."""
        pool, _ = _make_pool()
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        first_line = message.splitlines()[0]
        assert first_line.startswith("\U0001f4ca Daily Digest —")

    @pytest.mark.asyncio
    async def test_digest_second_line_is_blank(self):
        """Digest has a blank line separating the header from the data."""
        pool, _ = _make_pool()
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        lines = message.splitlines()
        assert lines[1] == ""

    @pytest.mark.asyncio
    async def test_digest_within_max_length(self):
        """Digest is at most MAX_DIGEST_LENGTH characters."""
        # Use many actions to stress the actions breakdown
        action_rows = [
            {"action_type": f"action_type_very_long_name_{i}", "n": i + 1}
            for i in range(20)
        ]
        pool, _ = _make_pool(action_rows=action_rows, feedback_count=5)
        scoped_push, notify = _make_scoped_push()

        await run(str(uuid.uuid4()), pool, scoped_push)

        message = notify.call_args.args[0]
        assert len(message) <= 800

    @pytest.mark.asyncio
    async def test_outcome_summary_contains_query_count(self):
        """Outcome summary includes the query count."""
        pool, _ = _make_pool(query_count=7)
        scoped_push, _ = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert "7" in result

    @pytest.mark.asyncio
    async def test_outcome_summary_contains_cost(self):
        """Outcome summary includes the formatted cost."""
        pool, _ = _make_pool(cost_usd=0.1234)
        scoped_push, _ = _make_scoped_push()

        result = await run(str(uuid.uuid4()), pool, scoped_push)

        assert "$0.1234" in result
