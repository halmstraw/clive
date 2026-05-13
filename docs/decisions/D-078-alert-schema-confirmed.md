---
id: D-078
title: D-073 placeholder alert schema adopted as confirmed jointly-owned contract
status: Accepted
date: 2026-05-01
blocks: Block 4 (Interface/Egress), Block 25 (Observability), Block 29 (Documentation)
agents: Experience Agent (Block 4), Infrastructure Agent (Block 25)
---

## Context
D-073 established a placeholder alert schema to unblock Block 25
implementation. The schema required formal adoption as the confirmed
jointly-owned contract (D-059) before being treated as stable.

## Options Considered
A. Adopt D-073 schema as-is (chosen) — severity encodes urgency sufficiently
   for v0.1; no additional fields needed yet.
B. Add a requires_acknowledgement field — adds complexity before there is
   evidence severity-based rendering is insufficient.

## Decision
The D-073 placeholder alert payload schema is adopted as the confirmed
jointly-owned contract between Block 25 and Block 4. No additional fields
are required at v0.1. Urgency is derived from the severity field alone:
error = act on this, warn = be aware, info = FYI. The schema is confirmed
and neither block may change it unilaterally (D-059).

Note: D-082 records that the attribution of Experience Agent review in this
decision is a misattribution — the Experience Agent was not in session when
D-078 was recorded. The schema content is binding; the attribution is not
accurate precedent.

## Rationale
Severity encodes urgency sufficiently for v0.1. Adding a
requires_acknowledgement field before there is evidence that severity-based
rendering is insufficient adds complexity Block 25 must populate correctly
on every alert.

## Consequences
Rules out adding further fields to the alert schema at v0.1 without a
superseding decision. Rules out any unilateral change to the schema by
either Block 25 or Block 4.

## Related Decisions
D-059 (jointly-owned alert schema), D-073 (placeholder schema),
D-082 (attribution correction for this decision).
