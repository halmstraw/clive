"""Tests for query handler."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.handler import _compute_confidence, _detect_action_intent


def test_detect_action_intent_found():
    assert _detect_action_intent("send an email to Alice") == "send"


def test_detect_action_intent_none():
    assert _detect_action_intent("what is the capital of France?") is None


def test_compute_confidence_above_threshold():
    chunks = [{"relevance_score": 0.8}, {"relevance_score": 0.5}]
    result = _compute_confidence(chunks)
    assert result["threshold_met"] is True
    assert result["chunks_returned"] == 2
    assert result["highest_relevance_score"] == pytest.approx(0.8)


def test_compute_confidence_empty():
    result = _compute_confidence([])
    assert result["threshold_met"] is False
    assert result["chunks_returned"] == 0
    assert result["highest_relevance_score"] == pytest.approx(0.0)


def test_compute_confidence_below_threshold():
    chunks = [{"relevance_score": 0.1}]
    result = _compute_confidence(chunks)
    assert result["threshold_met"] is False
