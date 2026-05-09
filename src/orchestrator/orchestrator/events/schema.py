"""Event schema — all CLIVE events are instances of CLIVEEvent.

Pydantic models for validation and serialisation.
D-025: all events carry event_id for idempotency.
D-030: bridge-origin events carry provenance metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Provenance(str, Enum):
    PRODUCTION = "production"
    BRIDGE = "bridge"  # Experimental zone origin — D-030


class CLIVEEvent(BaseModel):
    """Base event. Every inter-block communication is a CLIVEEvent."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    source_block: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    conversation_id: uuid.UUID | None = None
    zone_scope: str = "personal"  # D-050: hard-coded at v0.1
    provenance: Provenance = Provenance.PRODUCTION
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def collect_extras_into_payload(cls, values):
        declared = {
            'event_id', 'event_type', 'source_block', 'timestamp',
            'conversation_id', 'zone_scope', 'provenance', 'payload'
        }
        extras = {k: v for k, v in values.items() if k not in declared}
        if extras:
            existing_payload = values.get('payload', {}) or {}
            values['payload'] = {**existing_payload, **extras}
            for k in extras:
                del values[k]
        return values

    class Config:
        use_enum_values = True


class AlignmentResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ENHANCED_PASS = "enhanced_pass"
    ENHANCED_FAIL = "enhanced_fail"
