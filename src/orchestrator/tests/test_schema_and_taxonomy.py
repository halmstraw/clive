"""Tests for events/schema.py — CLIVEEvent model coverage."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from orchestrator.events.schema import AlignmentResult, CLIVEEvent, Provenance


class TestCLIVEEventDefaults:
    def test_event_id_auto_generated(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert isinstance(event.event_id, uuid.UUID)

    def test_timestamp_auto_generated(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert isinstance(event.timestamp, datetime)

    def test_zone_scope_defaults_to_personal(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert event.zone_scope == "personal"

    def test_provenance_defaults_to_production(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert event.provenance == Provenance.PRODUCTION

    def test_payload_defaults_to_empty_dict(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert event.payload == {}

    def test_conversation_id_defaults_to_none(self):
        event = CLIVEEvent(event_type="query.received", source_block=23)
        assert event.conversation_id is None


class TestCLIVEEventConstruction:
    def test_explicit_event_id(self):
        eid = uuid.uuid4()
        event = CLIVEEvent(event_id=eid, event_type="test", source_block=8)
        assert event.event_id == eid

    def test_payload_set_directly(self):
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            payload={"input_text": "hello"},
        )
        assert event.payload["input_text"] == "hello"

    def test_extra_fields_collected_into_payload(self):
        """Extra kwargs that aren't declared fields go into payload."""
        event = CLIVEEvent(
            event_type="query.received",
            source_block=23,
            input_text="hi",
        )
        assert "input_text" in event.payload

    def test_conversation_id_set(self):
        cid = uuid.uuid4()
        event = CLIVEEvent(event_type="test", source_block=8, conversation_id=cid)
        assert event.conversation_id == cid

    def test_bridge_provenance(self):
        event = CLIVEEvent(
            event_type="test",
            source_block=13,
            provenance=Provenance.BRIDGE,
        )
        assert event.provenance == Provenance.BRIDGE


class TestAlignmentResult:
    def test_pass_value(self):
        assert AlignmentResult.PASS == "pass"

    def test_fail_value(self):
        assert AlignmentResult.FAIL == "fail"

    def test_enhanced_pass_value(self):
        assert AlignmentResult.ENHANCED_PASS == "enhanced_pass"

    def test_enhanced_fail_value(self):
        assert AlignmentResult.ENHANCED_FAIL == "enhanced_fail"


class TestProvenance:
    def test_production_value(self):
        assert Provenance.PRODUCTION == "production"

    def test_bridge_value(self):
        assert Provenance.BRIDGE == "bridge"
