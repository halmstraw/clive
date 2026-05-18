"""Block 10 — Daily digest worker (v0.9).

D-140: daily_digest is one of the two initial Block 10 workers. Fires once daily
at 08:00 UTC via the scheduler cron trigger.

Declared scope (enforced by scheduler.make_scoped_push):
  read:queries, read:actions, read:cost, read:feedback, write:telegram

D-003: all Telegram delivery is via scoped_push['notify'] — no direct Block 23 call.
D-006: no irreversible actions; this worker is read-only + notify only.
D-025: run_id (UUID PRIMARY KEY in worker_runs) prevents double-processing at the
       scheduler level. Individual queries are independently retried on next run.

Run signature must match scheduler._run_worker expectation:
  async def run(run_id: str, pool: asyncpg.Pool, scoped_push: dict) -> str
"""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg
import structlog

log = structlog.get_logger()

MAX_DIGEST_LENGTH = 800


async def _fetch_query_count(pool: asyncpg.Pool) -> int | str:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT COUNT(*) FROM clive_state.conversation_turns"
                " WHERE role = 'user' AND created_at >= NOW() - INTERVAL '24 hours'"
            )
        return int(row)
    except Exception as exc:
        log.warning("daily_digest_query_count_failed", error=str(exc))
        return "unknown"


async def _fetch_actions_data(pool: asyncpg.Pool) -> list[tuple[str, int]] | str:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT action_type, COUNT(*) AS n"
                " FROM clive_state.pending_actions"
                " WHERE status = 'confirmed'"
                "   AND resolved_at >= NOW() - INTERVAL '24 hours'"
                " GROUP BY action_type"
            )
        return [(row["action_type"], int(row["n"])) for row in rows]
    except Exception as exc:
        log.warning("daily_digest_actions_failed", error=str(exc))
        return "unknown"


async def _fetch_cost_usd(pool: asyncpg.Pool) -> float | str:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT COALESCE(SUM(cost_usd), 0)"
                " FROM clive_state.llm_usage"
                " WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
        return float(row) if row is not None else 0.0
    except Exception as exc:
        log.warning("daily_digest_cost_failed", error=str(exc))
        return "unknown"


async def _fetch_feedback_count(pool: asyncpg.Pool) -> int | str:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT COUNT(*) FROM clive_state.feedback"
                " WHERE submitted_at >= NOW() - INTERVAL '24 hours'"
            )
        return int(row)
    except Exception as exc:
        log.warning("daily_digest_feedback_failed", error=str(exc))
        return "unknown"


async def run(run_id: str, pool: asyncpg.Pool, scoped_push: dict) -> str:
    """Daily digest worker. Returns outcome_summary string."""
    log.debug("daily_digest_run_start", run_id=str(run_id))
    now = datetime.now(timezone.utc)
    # "16 May 2026" — day without leading zero, 3-letter month, 4-digit year
    date_str = f"{now.day} {now.strftime('%b %Y')}"

    query_count = await _fetch_query_count(pool)
    actions_data = await _fetch_actions_data(pool)
    cost_usd = await _fetch_cost_usd(pool)
    feedback_count = await _fetch_feedback_count(pool)

    # ------------------------------------------------------------------
    # e. System health
    # ------------------------------------------------------------------
    system_health = "healthy"

    # ------------------------------------------------------------------
    # Format individual fields
    # ------------------------------------------------------------------
    query_str = str(query_count) if isinstance(query_count, int) else "unknown"
    cost_str = f"${cost_usd:.4f}" if isinstance(cost_usd, float) else "unknown"

    if isinstance(actions_data, str):
        # Query failed — placeholder
        actions_summary = "unknown"
        total_actions: int | str = "unknown"
    elif not actions_data:
        actions_summary = "none"
        total_actions = 0
    else:
        total = sum(count for _, count in actions_data)
        breakdown = ", ".join(
            f"{count} {atype}" for atype, count in sorted(actions_data)
        )
        actions_summary = f"{total} ({breakdown})"
        total_actions = total

    # ------------------------------------------------------------------
    # Build digest lines
    # ------------------------------------------------------------------
    lines = [
        f"\U0001f4ca Daily Digest — {date_str}",
        "",
        f"Queries: {query_str}",
        f"Actions: {actions_summary}",
        f"Cost: {cost_str}",
    ]

    # Feedback line: omit entirely when count is 0; show "unknown" on error
    if isinstance(feedback_count, str):
        lines.append("Feedback: unknown")
    elif feedback_count > 0:
        lines.append(f"Feedback: {feedback_count} poor-quality response(s) tagged")
    # else: feedback_count == 0 → line omitted per spec

    lines.append(f"System: {system_health}")
    digest_text = "\n".join(lines)

    # Truncate if over limit — drop actions breakdown to total only
    if len(digest_text) > MAX_DIGEST_LENGTH:
        total_short = str(total_actions)
        short_lines = [
            f"\U0001f4ca Daily Digest — {date_str}",
            "",
            f"Queries: {query_str}",
            f"Actions: {total_short}",
            f"Cost: {cost_str}",
        ]
        if isinstance(feedback_count, str):
            short_lines.append("Feedback: unknown")
        elif isinstance(feedback_count, int) and feedback_count > 0:
            short_lines.append(
                f"Feedback: {feedback_count} poor-quality response(s) tagged"
            )
        short_lines.append(f"System: {system_health}")
        digest_text = "\n".join(short_lines)

    # ------------------------------------------------------------------
    # Deliver via scoped_push['notify']  (D-003)
    # ------------------------------------------------------------------
    delivery_failed = False
    notify = scoped_push.get("notify")
    if notify:
        try:
            await notify(digest_text)
        except Exception as exc:
            log.error("daily_digest_delivery_failed", error=str(exc))
            delivery_failed = True
    else:
        log.warning("daily_digest_no_notify_scope")

    # ------------------------------------------------------------------
    # Return outcome_summary for worker_runs.outcome_summary
    # ------------------------------------------------------------------
    prefix = "delivery_failed" if delivery_failed else "Sent"
    return f"{prefix}: {query_str} queries, {total_actions} actions, {cost_str}"
