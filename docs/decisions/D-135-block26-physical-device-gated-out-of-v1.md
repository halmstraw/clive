# D-135 — Block 26 (Physical Device/Edge Node) gated out of v1 scope

**Status:** Accepted  
**Date:** 2026-05-16  
**Blocks affected:** Block 26 (Physical Device/Edge Node), Block 2 (Multi-Surface), Block 5 (Sync/State Layer)  
**Recorded by:** Architect

---

## Context

During v1 roadmap planning, the Architect identified that Block 26 (Physical
Device/Edge Node) has hard dependencies on Block 2 (Multi-Surface) and
Block 5 (Sync/State Layer), neither of which were implemented at the time of
this decision. Building Block 26 without the software substrate in place would
produce a dead-end hardware artefact that cannot integrate with the rest of
the system.

Block 26 is also a hardware procurement and embedded firmware project — a
qualitatively different type of work from the software-only blocks that make
up the rest of v1.

The owner confirmed this gating call during v1 roadmap review.

---

## Decision

Block 26 (Physical Device/Edge Node) is explicitly gated out of v1 scope.

It will not be implemented until:
1. Block 2 (Multi-Surface) is complete
2. Block 5 (Sync/State Layer) is complete
3. A formal owner decision activates Block 26 work

This gate must be superseded by an explicit decision before any Block 26
implementation work begins. It does not supersede itself on version number
alone.

---

## Alternatives considered

**Include Block 26 in v1** — rejected. There is no software substrate for it
to integrate with until Blocks 2 and 5 exist. Building it now produces orphaned
hardware work.

**Defer the decision to later** — rejected. The roadmap requires explicit
scope boundaries to be useful. Leaving this ambiguous would create uncertainty
in v0.11 (Multi-Surface) planning about whether physical device integration
is in scope.

---

## Impact

- Block 26 is excluded from all v1 version scopes (v0.8 through v1.0)
- v1.0 sign-off criteria do not require Block 26 to be implemented
- Blocks 30–38 (Business Layer, D-036) remain separately gated and are
  unaffected by this decision
