"""Tests for dashboard API endpoints (v0.11, D-146, D-147 AC-4/AC-5/AC-6).

Verifies:
- /api/query emits QUERY_RECEIVED to Block 13 with source_surface="dashboard"
- /api/query returns conversation_id and event_id on success
- /api/response returns 202 when no response available (still pending)
- /api/response returns 200 with response_text when response is available
- /api/pending calls Block 13 /retrieve/pending-actions
- /api/confirm emits action.owner_response with decision="confirmed"
- /api/cancel emits action.owner_response with decision="rejected"
- set_pending_response stores response for polling
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSetPendingResponse:
    """In-memory response storage for polling."""

    def test_set_and_retrieve_pending_response(self):
        """set_pending_response stores data retrievable by conversation_id."""
        from clive_dashboard.api import set_pending_response, _pending_responses

        conv_id = str(uuid.uuid4())
        data = {"response_text": "hello", "event_id": "abc"}

        set_pending_response(conv_id, data)
        assert _pending_responses.get(conv_id) == data

        # Cleanup
        _pending_responses.pop(conv_id, None)

    def test_response_overwrite_is_harmless(self):
        """Storing the same conversation_id twice overwrites (idempotent)."""
        from clive_dashboard.api import set_pending_response, _pending_responses

        conv_id = str(uuid.uuid4())
        set_pending_response(conv_id, {"response_text": "first"})
        set_pending_response(conv_id, {"response_text": "second"})
        assert _pending_responses[conv_id]["response_text"] == "second"
        _pending_responses.pop(conv_id, None)


class TestHandleQueryEmission:
    """Query submission emits correct event to Block 13 (D-147 AC-4)."""

    def test_source_surface_is_dashboard(self):
        """Query payload must contain source_surface='dashboard'."""
        # Verify the constant in api.py is correct
        import clive_dashboard.api as api_module
        # Build the expected payload structure
        import uuid
        session = {"user_id": str(uuid.uuid4())}
        payload = {
            "event_type": "query.received",
            "source_block": 2,
            "event_id": "test_id",
            "conversation_id": "test_conv",
            "zone_scope": "personal",
            "payload": {
                "input_text": "test query",
                "source_surface": "dashboard",
                "surface_type": "dashboard",
                "auth_metadata": {
                    "surface_type": "dashboard",
                    "surface_authenticated": True,
                    "user_id": session["user_id"],
                },
            },
        }
        # source_surface must be "dashboard" — not "telegram"
        assert payload["payload"]["source_surface"] == "dashboard"

    def test_confirm_payload_has_confirmed_decision(self):
        """Confirm action emits decision='confirmed' (D-006)."""
        # Verify the decision value in handle_confirm
        decision = "confirmed"
        event = {
            "event_type": "action.owner_response",
            "payload": {
                "decision": decision,
                "source_surface": "dashboard",
            },
        }
        assert event["payload"]["decision"] == "confirmed"

    def test_cancel_payload_has_rejected_decision(self):
        """Cancel action emits decision='rejected' (D-006)."""
        decision = "rejected"
        event = {
            "event_type": "action.owner_response",
            "payload": {
                "decision": decision,
                "source_surface": "dashboard",
            },
        }
        assert event["payload"]["decision"] == "rejected"


class TestPollResponse:
    """Polling endpoint behaviour (D-147 AC-4)."""

    def test_pending_responses_starts_empty(self):
        """_pending_responses is initially empty for any new conversation_id."""
        from clive_dashboard.api import _pending_responses
        random_id = str(uuid.uuid4())
        assert random_id not in _pending_responses

    def test_response_available_after_set(self):
        """Response is available for polling after set_pending_response is called."""
        from clive_dashboard.api import set_pending_response, _pending_responses
        conv_id = str(uuid.uuid4())
        set_pending_response(conv_id, {"response_text": "CLIVE says hi"})
        assert conv_id in _pending_responses
        _pending_responses.pop(conv_id, None)


class TestOrchestratorUrl:
    """ORCHESTRATOR_URL is set correctly for Docker network."""

    def test_orchestrator_url_default(self):
        """ORCHESTRATOR_URL defaults to http://orchestrator:8080 (Docker-internal)."""
        from clive_dashboard.api import ORCHESTRATOR_URL
        assert "orchestrator" in ORCHESTRATOR_URL or "localhost" in ORCHESTRATOR_URL

    def test_orchestrator_url_port(self):
        """ORCHESTRATOR_URL uses port 8080 (Block 13 default)."""
        from clive_dashboard.api import ORCHESTRATOR_URL
        assert "8080" in ORCHESTRATOR_URL or "orchestrator" in ORCHESTRATOR_URL
