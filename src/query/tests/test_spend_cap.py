"""Unit tests for Block 20 spend cap logic — D-126 criteria 1 and 2.

All tests mock the DB pool and LLM client.
No live DB or LLM calls are made in CI.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.spend import compute_cost, get_daily_cap, get_today_spend_usd


# ---------------------------------------------------------------------------
# compute_cost — pricing dict
# ---------------------------------------------------------------------------

def test_compute_cost_known_model_sonnet():
    """Known model pricing returns non-zero cost."""
    cost = compute_cost(
        "anthropic/claude-sonnet-4-20250514",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert abs(cost - 0.0105) < 1e-9


def test_compute_cost_known_model_haiku():
    cost = compute_cost(
        "anthropic/claude-3-haiku-20240307",
        prompt_tokens=2000,
        completion_tokens=1000,
    )
    assert abs(cost - 0.00175) < 1e-9


def test_compute_cost_unknown_model_returns_zero():
    """Unknown models return 0.0 without raising (D-125)."""
    cost = compute_cost("unknown/mystery-model", prompt_tokens=100, completion_tokens=50)
    assert cost == pytest.approx(0.0)


def test_compute_cost_zero_tokens():
    cost = compute_cost("anthropic/claude-sonnet-4-20250514", 0, 0)
    assert cost == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# get_daily_cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_daily_cap_set():
    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": "10.50"}),
        patch("query.spend.get_daily_cap_from_config", AsyncMock(return_value=None)),
    ):
        assert await get_daily_cap() == pytest.approx(10.50)


@pytest.mark.asyncio
async def test_get_daily_cap_unset():
    import os
    os.environ.pop("DAILY_SPEND_CAP_USD", None)
    with patch("query.spend.get_daily_cap_from_config", AsyncMock(return_value=None)):
        assert await get_daily_cap() is None


@pytest.mark.asyncio
async def test_get_daily_cap_empty_string():
    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": ""}),
        patch("query.spend.get_daily_cap_from_config", AsyncMock(return_value=None)),
    ):
        assert await get_daily_cap() is None


@pytest.mark.asyncio
async def test_get_daily_cap_invalid_value():
    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": "not-a-number"}),
        patch("query.spend.get_daily_cap_from_config", AsyncMock(return_value=None)),
    ):
        assert await get_daily_cap() is None


@pytest.mark.asyncio
async def test_get_daily_cap_prefers_config_over_env():
    """Config table value takes precedence over env var (D-149)."""
    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": "10.00"}),
        patch("query.spend.get_daily_cap_from_config", AsyncMock(return_value=5.0)),
    ):
        assert await get_daily_cap() == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# get_today_spend_usd — DB mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_today_spend_usd_returns_sum():
    mock_row = {"total": 3.1415}
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    with patch("query.spend.get_pool", return_value=mock_pool):
        result = await get_today_spend_usd()

    assert abs(result - 3.1415) < 1e-9


@pytest.mark.asyncio
async def test_get_today_spend_usd_returns_zero_on_db_error():
    """DB failure is non-fatal — returns 0.0 (errs on side of allowing call)."""
    with patch("query.spend.get_pool", side_effect=RuntimeError("pool not ready")):
        result = await get_today_spend_usd()
    assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# handle_query — spend cap gate (D-126 criterion 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spend_cap_blocks_llm_call_and_emits_event():
    """When today's spend >= cap: canned response returned, LLM not called,
    cost.cap_exceeded event emitted. D-126 criterion 2."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "What is the capital of France?",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    emitted_events: list[dict] = []

    def fake_emit(event_type: str, payload: dict) -> None:
        emitted_events.append({"event_type": event_type, **payload})

    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": "1.00"}),
        patch("query.handler.get_today_spend_usd", AsyncMock(return_value=1.50)),
        patch("query.handler.get_daily_cap", return_value=1.00),
        patch("query.handler._emit_event", side_effect=fake_emit),
        patch("query.handler.llm.complete", AsyncMock()) as mock_llm,
        # Mock orchestrator HTTP calls for system docs and retrieval
        patch("query.handler.httpx.AsyncClient") as mock_http,
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "document_content": "personality",
            "ranked_chunks": [],
        })
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

        from query.handler import handle_query
        await handle_query(event)

    # LLM must NOT have been called
    mock_llm.assert_not_called()

    # cost.cap_exceeded must have been emitted
    cap_events = [e for e in emitted_events if e["event_type"] == "cost.cap_exceeded"]
    assert len(cap_events) == 1
    assert cap_events[0]["cap_usd"] == pytest.approx(1.00)

    # query.response must have been emitted (canned message)
    response_events = [e for e in emitted_events if e["event_type"] == "query.response"]
    assert len(response_events) == 1
    assert "cap" in response_events[0]["response_text"].lower()


@pytest.mark.asyncio
async def test_spend_below_cap_calls_llm():
    """When today's spend < cap: LLM is called normally. D-126 criterion 2."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "Tell me something interesting.",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    with (
        patch.dict("os.environ", {"DAILY_SPEND_CAP_USD": "10.00"}),
        patch("query.handler.get_today_spend_usd", AsyncMock(return_value=0.50)),
        patch("query.handler.get_daily_cap", return_value=10.00),
        patch("query.handler._emit_event", AsyncMock()),
        patch("query.handler.llm.complete", AsyncMock(
            return_value=("Response text.", {"model": "anthropic/claude-sonnet-4-20250514", "prompt_tokens": 100, "completion_tokens": 50})
        )) as mock_llm,
        patch("query.handler.record_usage", AsyncMock()),
        patch("query.handler.httpx.AsyncClient") as mock_http,
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "document_content": "content",
            "ranked_chunks": [],
        })
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

        from query.handler import handle_query
        await handle_query(event)

    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_no_cap_set_always_calls_llm():
    """When DAILY_SPEND_CAP_USD is unset: LLM always called regardless of spend."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "Hello.",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    import os
    os.environ.pop("DAILY_SPEND_CAP_USD", None)

    with (
        patch("query.handler.get_today_spend_usd", AsyncMock(return_value=999.99)),
        patch("query.handler.get_daily_cap", return_value=None),
        patch("query.handler._emit_event", AsyncMock()),
        patch("query.handler.llm.complete", AsyncMock(
            return_value=("Hello back.", {"model": "anthropic/claude-sonnet-4-20250514", "prompt_tokens": 10, "completion_tokens": 5})
        )) as mock_llm,
        patch("query.handler.record_usage", AsyncMock()),
        patch("query.handler.httpx.AsyncClient") as mock_http,
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "document_content": "content",
            "ranked_chunks": [],
        })
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

        from query.handler import handle_query
        await handle_query(event)

    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_usage_record_inserted_after_llm_call():
    """record_usage is called with correct model/tokens after a successful LLM call."""
    event = {
        "event_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "input_text": "What is 2+2?",
        "zone_scope": "personal",
        "conversation_history": [],
    }

    import os
    os.environ.pop("DAILY_SPEND_CAP_USD", None)

    mock_record = AsyncMock()

    with (
        patch("query.handler.get_daily_cap", return_value=None),
        patch("query.handler._emit_event", AsyncMock()),
        patch("query.handler.llm.complete", AsyncMock(
            return_value=("Four.", {"model": "anthropic/claude-3-haiku-20240307", "prompt_tokens": 20, "completion_tokens": 3})
        )),
        patch("query.handler.record_usage", mock_record),
        patch("query.handler.httpx.AsyncClient") as mock_http,
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "document_content": "content",
            "ranked_chunks": [],
        })
        mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=mock_resp)
        ))
        mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

        from query.handler import handle_query
        await handle_query(event)

    mock_record.assert_called_once()
    call_args = mock_record.call_args
    assert call_args.args[0] == "anthropic/claude-3-haiku-20240307"  # model
    assert call_args.args[1] == 20   # prompt_tokens
    assert call_args.args[2] == 3    # completion_tokens
    assert call_args.args[3] > 0     # cost_usd > 0 for known model
