"""Tests for alignment gate."""

from orchestrator.alignment import check
from orchestrator.events.schema import AlignmentResult, CLIVEEvent, Provenance
from orchestrator.events.taxonomy import ACTION_PROPOSED, VARIANT_PROMOTED


def test_standard_pass():
    event = CLIVEEvent(event_type="query.received", source_block=23)
    assert check(event) == AlignmentResult.PASS


def test_destructive_action_rejected():
    event = CLIVEEvent(
        event_type=ACTION_PROPOSED,
        source_block=8,
        payload={"destructive": True},
    )
    assert check(event) == AlignmentResult.FAIL


def test_evolution_targeting_personality_rejected():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        payload={"target_block": 1},
    )
    assert check(event) == AlignmentResult.FAIL


def test_bridge_event_passes_enhanced_gate():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        provenance=Provenance.BRIDGE,
        payload={
            "provenance_metadata": {"experimental_zone_id": "exp-01"},
            "fitness_scores": {"accuracy": 0.9, "cost": 0.1},
        },
    )
    assert check(event) == AlignmentResult.ENHANCED_PASS


def test_bridge_event_missing_provenance_rejected():
    event = CLIVEEvent(
        event_type=VARIANT_PROMOTED,
        source_block=21,
        provenance=Provenance.BRIDGE,
        payload={},  # Missing provenance_metadata
    )
    assert check(event) == AlignmentResult.ENHANCED_FAIL
