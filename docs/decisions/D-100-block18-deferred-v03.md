---
id: D-100
title: Block 18 (Feedback/Correction) deferred to v0.3
status: Accepted
date: 2026-05-09
blocks: Block 18 (Feedback/Correction)
agents: Knowledge Agent
---

## Context
Block 18 (Feedback/Correction) provides the mechanism for the owner to
correct CLIVE's knowledge and behaviour. It was under consideration for v0.2
scope but requires Block 14, 15, and 16 to be stable first.

## Options Considered
A. Defer Block 18 to v0.3 (chosen) — Block 14, 15, and 16 must be stable
   before feedback and correction mechanisms are meaningful.
B. Include Block 18 in v0.2 — premature; feedback loop cannot be designed
   until the ingestion pipeline it corrects is operational.

## Decision
Block 18 (Feedback/Correction) is deferred to v0.3. It is out of v0.2 scope.
Block 14, 15, and 16 must be operational before Block 18 work begins.

## Rationale
A feedback and correction mechanism requires a stable substrate to correct.
Building Block 18 before the ingestion and storage pipeline is operational
and tested would produce a feedback loop with nothing to feed back into.

## Consequences
Rules out Block 18 work in v0.2. Block 18 requirements work may proceed in
parallel if needed, but implementation is v0.3.

## Related Decisions
D-099 (v0.2 scope), D-014 (Block 14 ingestion), D-015 (Block 15 processing),
D-016 (Block 16 storage).
