"""Block 22 alignment gate — rules-and-schema implementation.

D-037: deterministic rules, closed failure.
D-030: bridge-origin events route through enhanced gate.
D-004: goal function protection.
D-005: personality protection.

Rules are loaded from the alignment constitution document stored
in Block 16. At v0.1 they are also expressed here as code for
bootstrap — the Block 16 version takes precedence once the
system is operational.
"""

from __future__ import annotations

import structlog

from .events.schema import AlignmentResult, CLIVEEvent, Provenance
from .events.taxonomy import (
    ACTION_PROPOSED,
    EVOLUTION_BOUNDARY_BREACH,
    VARIANT_CREATED,
    VARIANT_EVALUATED,
    VARIANT_PROMOTED,
    VARIANT_RETIRED,
)

log = structlog.get_logger()

# Evolution event types that may target protected parameters
EVOLUTION_EVENT_TYPES = {
    VARIANT_CREATED,
    VARIANT_EVALUATED,
    VARIANT_PROMOTED,
    VARIANT_RETIRED,
}

# Block numbers for protected components
BLOCK_PERSONALITY = 1
BLOCK_ALIGNMENT = 22


def _check_standard(event: CLIVEEvent) -> tuple[bool, str]:
    """Standard alignment check applied to all production events.

    Returns (passed, reason). Closed failure: if any check fails,
    the event is rejected.
    """
    # Irreversible action gate — route to confirmation, not execution
    if event.event_type == ACTION_PROPOSED:
        payload = event.payload
        if payload.get("destructive", False):
            return False, "destructive_action_requires_confirmation"

    # Personality protection — D-005
    if event.event_type in EVOLUTION_EVENT_TYPES:
        target = event.payload.get("target_block")
        if target == BLOCK_PERSONALITY:
            return False, "evolution_targeting_personality_block"

    # Goal function protection — D-004
    if event.event_type in EVOLUTION_EVENT_TYPES:
        if event.payload.get("modifies_alignment_constitution", False):
            return False, "evolution_modifying_alignment_constitution"

    # Deception check — declared intent must match payload
    declared_type = event.payload.get("declared_event_type")
    if declared_type and declared_type != event.event_type:
        return False, "declared_intent_mismatch"

    # Zone boundary check
    payload_zone = event.payload.get("zone_of_origin")
    if payload_zone and payload_zone != event.zone_scope:
        # Cross-zone data without explicit permission
        if not event.payload.get("cross_zone_permitted", False):
            return False, "zone_boundary_violation"

    return True, "pass"


def _check_enhanced(event: CLIVEEvent) -> tuple[bool, str]:
    """Enhanced alignment gate for bridge-origin events — D-030.

    Superset of standard check. Stricter provenance and mutation
    boundary checks. Closed failure is absolute.
    """
    # Provenance integrity
    if event.provenance != Provenance.BRIDGE:
        return False, "enhanced_gate_called_on_non_bridge_event"

    provenance_meta = event.payload.get("provenance_metadata", {})
    if not provenance_meta.get("experimental_zone_id"):
        return False, "missing_experimental_zone_id"

    # Mutation boundary — cannot affect alignment or personality
    if event.payload.get("modifies_alignment_constitution", False):
        return False, "bridge_event_modifying_alignment_constitution"

    if event.payload.get("target_block") == BLOCK_PERSONALITY:
        return False, "bridge_event_targeting_personality"

    # Fitness signal conformance
    if event.event_type in (VARIANT_EVALUATED, VARIANT_PROMOTED):
        if "fitness_scores" not in event.payload:
            return False, "fitness_signal_missing_required_fields"

    # Novelty flag — route to owner awareness before proceeding
    if event.payload.get("novel_capability", False):
        return False, "novel_capability_requires_owner_review"

    # Run standard checks as well
    passed, reason = _check_standard(event)
    if not passed:
        return False, f"enhanced_standard_check_failed:{reason}"

    return True, "enhanced_pass"


def check(event: CLIVEEvent) -> AlignmentResult:
    """Run the appropriate alignment gate for this event.

    Bridge-origin events → enhanced gate.
    Production events → standard gate.

    Returns AlignmentResult. Never raises — closed failure means FAIL.
    """
    try:
        if event.provenance == Provenance.BRIDGE:
            passed, reason = _check_enhanced(event)
            result = AlignmentResult.ENHANCED_PASS if passed else AlignmentResult.ENHANCED_FAIL
        else:
            passed, reason = _check_standard(event)
            result = AlignmentResult.PASS if passed else AlignmentResult.FAIL

        log.info(
            "alignment_check",
            event_id=str(event.event_id),
            event_type=event.event_type,
            result=result,
            reason=reason,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        # Closed failure — any exception is treated as a rejection
        log.error(
            "alignment_check_exception",
            event_id=str(event.event_id),
            exc=str(exc),
        )
        return AlignmentResult.FAIL
