"""Extended alignment gate tests — covering remaining code paths."""
from __future__ import annotations

import pytest

from orchestrator.alignment import check, _check_standard, _check_enhanced
from orchestrator.events.schema import AlignmentResult, CLIVEEvent, Provenance
from orchestrator.events.taxonomy import (
    VARIANT_CREATED,
    VARIANT_EVALUATED,
    VARIANT_PROMOTED,
    VARIANT_RETIRED,
)


# ---------------------------------------------------------------------------
# _check_standard — remaining paths
# ---------------------------------------------------------------------------

class TestCheckStandardExtended:
    def test_evolution_modifying_alignment_constitution_rejected(self):
        event = CLIVEEvent(
            event_type=VARIANT_PROMOTED,
            source_block=21,
            payload={"modifies_alignment_constitution": True},
        )
        passed, reason = _check_standard(event)
        assert not passed
        assert "alignment_constitution" in reason

    def test_declared_intent_mismatch_rejected(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={"declared_event_type": "action.proposed"},
        )
        passed, reason = _check_standard(event)
        assert not passed
        assert "mismatch" in reason

    def test_declared_intent_matches_passes(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={"declared_event_type": "query.received"},
        )
        passed, reason = _check_standard(event)
        assert passed

    def test_zone_boundary_violation_rejected(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            zone_scope="personal",
            payload={"zone_of_origin": "work", "cross_zone_permitted": False},
        )
        passed, reason = _check_standard(event)
        assert not passed
        assert "zone" in reason

    def test_zone_boundary_with_cross_zone_permitted_passes(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            zone_scope="personal",
            payload={"zone_of_origin": "work", "cross_zone_permitted": True},
        )
        passed, reason = _check_standard(event)
        assert passed

    def test_no_zone_payload_passes(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={},
        )
        passed, _ = _check_standard(event)
        assert passed


# ---------------------------------------------------------------------------
# _check_enhanced — remaining paths
# ---------------------------------------------------------------------------

class TestCheckEnhancedExtended:
    def _base_bridge_event(self, payload: dict) -> CLIVEEvent:
        return CLIVEEvent(
            event_type=VARIANT_PROMOTED,
            source_block=21,
            provenance=Provenance.BRIDGE,
            payload={
                "provenance_metadata": {"experimental_zone_id": "exp-01"},
                "fitness_scores": {"accuracy": 0.9},
                **payload,
            },
        )

    def test_non_bridge_event_rejects_enhanced_gate(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            provenance=Provenance.PRODUCTION,
        )
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "non_bridge" in reason

    def test_bridge_modifying_alignment_constitution_rejected(self):
        event = self._base_bridge_event({"modifies_alignment_constitution": True})
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "alignment" in reason

    def test_bridge_targeting_personality_rejected(self):
        event = self._base_bridge_event({"target_block": 1})
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "personality" in reason

    def test_variant_evaluated_missing_fitness_scores_rejected(self):
        event = CLIVEEvent(
            event_type=VARIANT_EVALUATED,
            source_block=21,
            provenance=Provenance.BRIDGE,
            payload={
                "provenance_metadata": {"experimental_zone_id": "exp-01"},
                # No fitness_scores
            },
        )
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "fitness" in reason

    def test_novel_capability_rejected(self):
        event = self._base_bridge_event({"novel_capability": True})
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "novel" in reason

    def test_bridge_event_with_standard_check_failure(self):
        """Bridge event that passes enhanced checks but fails standard check."""
        event = CLIVEEvent(
            event_type=VARIANT_PROMOTED,
            source_block=21,
            provenance=Provenance.BRIDGE,
            payload={
                "provenance_metadata": {"experimental_zone_id": "exp-01"},
                "fitness_scores": {"accuracy": 0.9},
                "declared_event_type": "wrong_event_type",  # fails standard check
            },
        )
        passed, reason = _check_enhanced(event)
        assert not passed
        assert "standard" in reason


# ---------------------------------------------------------------------------
# check() — exception path
# ---------------------------------------------------------------------------

class TestCheckExceptionPath:
    def test_exception_in_check_returns_fail(self, monkeypatch):
        """Any exception in the alignment check returns FAIL — closed failure."""
        from orchestrator import alignment

        def broken_standard(event):
            raise RuntimeError("Simulated error")

        monkeypatch.setattr(alignment, "_check_standard", broken_standard)

        event = CLIVEEvent(event_type="query.received", source_block=23)
        result = check(event)
        assert result == AlignmentResult.FAIL


# ---------------------------------------------------------------------------
# Scheduler — make_scoped_push and _get_pool
# ---------------------------------------------------------------------------

class TestSchedulerMakeScopedPush:
    def test_write_telegram_scope_grants_notify(self):
        from orchestrator.scheduler import make_scoped_push

        scoped = make_scoped_push("daily_digest", ["write:telegram"])
        assert "notify" in scoped
        assert callable(scoped["notify"])

    def test_write_confirmations_scope_grants_request_confirmation(self):
        from orchestrator.scheduler import make_scoped_push

        scoped = make_scoped_push("knowledge_maintenance", ["write:confirmations"])
        assert "request_confirmation" in scoped

    def test_no_scope_grants_nothing(self):
        from orchestrator.scheduler import make_scoped_push

        scoped = make_scoped_push("bare_worker", [])
        assert "notify" not in scoped
        assert "request_confirmation" not in scoped

    def test_both_scopes_grants_both(self):
        from orchestrator.scheduler import make_scoped_push

        scoped = make_scoped_push("worker", ["write:telegram", "write:confirmations"])
        assert "notify" in scoped
        assert "request_confirmation" in scoped


class TestSchedulerGetPool:
    def test_get_pool_raises_when_not_init(self):
        from orchestrator import scheduler

        original = scheduler._pool
        try:
            scheduler._pool = None
            with pytest.raises(RuntimeError, match="Scheduler pool not initialised"):
                scheduler._get_pool()
        finally:
            scheduler._pool = original


class TestSchedulerPushWorkerNotification:
    @pytest.mark.asyncio
    async def test_sends_notification_to_telegram(self):
        from orchestrator.scheduler import _push_worker_notification
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await _push_worker_notification("Daily digest ready")

        mock_client.post.assert_called_once()
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["severity"] == "info"
        assert "Daily digest ready" in call_json["body"]
