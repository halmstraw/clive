---
id: D-082
title: D-078 attribution to Experience Agent corrected — agent was not in session
status: Accepted
date: 2026-05-01
blocks: Block 4 (Interface/Egress), Block 25 (Observability), Block 29 (Documentation)
agents: Experience Agent, Infrastructure Agent (Block 25)
---

## Context
D-078 states "the Experience Agent has reviewed and accepted the schema on
behalf of Block 4." At the time D-078 was recorded, the Experience Agent was
not yet activated. D-008 requires decisions to be recorded accurately.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
D-078's statement that "the Experience Agent has reviewed and accepted the
schema on behalf of Block 4" is a misattribution. The owner adopted the alert
schema in the Experience Agent's absence. The schema itself is binding and
confirmed. If the Experience Agent identifies a required change in a future
session, that change follows the D-059 joint-ownership process and requires
a superseding decision.

Supersedes: The attribution clause in D-078 only — not the schema decision
itself.

## Rationale
D-008 requires decisions to be recorded accurately. D-078 contains an
attribution that does not reflect what actually happened. Leaving it
uncorrected would create a false precedent — that agent acknowledgement can
be asserted without the agent being in session.

## Consequences
Rules out treating D-078's attribution as accurate. Rules out using D-078
as precedent for asserting agent acknowledgement in an agent's absence.
The Experience Agent is bound by the schema's content (which is confirmed)
but may propose changes through D-059.

## Related Decisions
D-059 (jointly-owned alert schema), D-078 (schema confirmed — attribution
clause superseded by this decision).
