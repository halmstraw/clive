"""LLM spend tracking for Block 20 — Cost/Rate Management (D-125, v0.6).

Responsibilities:
  - Model pricing dict: known per-token USD prices. Unknown models → 0.0 + warning.
  - get_today_spend_usd(): daily spend sum from clive_state.llm_usage.
  - record_usage(): insert one row after a successful LLM call.
  - get_daily_cap(): read config table first, fall back to DAILY_SPEND_CAP_USD env var.
  - compute_cost(): prompt_tokens * prompt_price + completion_tokens * completion_price.

Keys in MODEL_PRICING match the CLIVE_LLM_MODEL env var format (provider/model).

v0.12: get_daily_cap() is now async. It reads clive_state.config for key
  daily_spend_cap_usd before falling back to the env var (D-149).
  Config table is the owner-managed source of truth; env var is bootstrap-only.
"""

from __future__ import annotations

import os
from decimal import Decimal

import structlog

from .db import get_pool

log = structlog.get_logger()

# Per-token prices in USD: (prompt_price, completion_price).
# Based on published pricing at time of D-125 (2026-05-15).
# Add overrides here as new models are deployed.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic Claude 3.5 Sonnet / Sonnet 4
    "anthropic/claude-3-5-sonnet-20241022":  (0.000003, 0.000015),
    "anthropic/claude-sonnet-4-20250514":    (0.000003, 0.000015),
    # Anthropic Claude 3 Haiku
    "anthropic/claude-3-haiku-20240307":     (0.00000025, 0.00000125),
    "anthropic/claude-3-haiku":              (0.00000025, 0.00000125),
    # OpenAI embeddings (Block 15 — included for completeness)
    "openai/text-embedding-3-small":         (0.00000002, 0.0),
}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated cost in USD for this call.

    Unknown models return 0.0 and log a warning — cost is not tracked
    but LLM call is not blocked (D-125: unknown models default cost = 0.0).
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        log.warning("unknown_model_pricing_defaulting_zero", model=model)
        return 0.0
    prompt_price, completion_price = pricing
    return round(prompt_tokens * prompt_price + completion_tokens * completion_price, 8)


async def get_daily_cap_from_config() -> float | None:
    """Query clive_state.config for daily_spend_cap_usd.

    Returns the float value if present and parseable, or None on any error
    (missing key, unparseable value, DB failure). Non-fatal throughout —
    callers fall back to the env var on None.
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config_value FROM clive_state.config WHERE config_key = 'daily_spend_cap_usd'"
            )
        if row is None:
            return None
        return float(row["config_value"])
    except (TypeError, ValueError) as exc:
        log.warning("invalid_config_daily_spend_cap", error=str(exc))
        return None
    except Exception as exc:
        log.warning("config_read_failed_spend_cap_fallback", error=str(exc))
        return None


async def get_daily_cap() -> float | None:
    """Return the active daily spend cap as float, or None (no cap).

    Reads clive_state.config first (owner-configured, D-149).
    Falls back to DAILY_SPEND_CAP_USD env var (bootstrap-only).
    Returns None if neither is set or parseable.
    """
    config_cap = await get_daily_cap_from_config()
    if config_cap is not None:
        return config_cap

    val = os.environ.get("DAILY_SPEND_CAP_USD", "").strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        log.warning("invalid_daily_spend_cap", value=val)
        return None


async def get_today_spend_usd() -> float:
    """Sum cost_usd from clive_state.llm_usage for today (UTC calendar day).

    Returns 0.0 on any DB error — non-fatal, errs on the side of allowing
    the LLM call through rather than blocking on DB failure.
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(cost_usd), 0.0) AS total
                FROM clive_state.llm_usage
                WHERE created_at >= CURRENT_DATE
                """
            )
        return float(row["total"]) if row else 0.0
    except Exception as exc:
        log.error("spend_read_failed", error=str(exc))
        return 0.0


async def record_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
) -> None:
    """Insert one row into clive_state.llm_usage after a successful LLM call.

    Failures are logged and non-fatal — a failed record write does not
    roll back the response that was already sent to the owner.
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clive_state.llm_usage
                    (model, prompt_tokens, completion_tokens, cost_usd)
                VALUES ($1, $2, $3, $4)
                """,
                model,
                prompt_tokens,
                completion_tokens,
                Decimal(str(cost_usd)),
            )
        log.info(
            "llm_usage_recorded",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    except Exception as exc:
        log.error(
            "llm_usage_record_failed",
            error=str(exc),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
