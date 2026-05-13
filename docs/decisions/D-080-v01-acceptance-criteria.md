---
id: D-080
title: Six acceptance criteria define when CLIVE v0.1 is shippable
status: Accepted
date: 2026-05-01
blocks: Block 1 (Personality), Block 8 (Query/RAG), Block 13 (Orchestrator),
        Block 16 (Storage), Block 22 (Alignment Layer), Block 23 (Security)
agents: All active agents for v0.1
---

## Context
D-035 defined v0.1 scope but left "done" undefined. Without explicit
acceptance criteria, v0.1 ships by feel or exhaustion rather than by
verified conditions.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
CLIVE v0.1 is shippable when all six criteria are simultaneously true:

1. Owner can send a message via Telegram and receive a personality-consistent,
   knowledge-grounded response.
2. Every event in that exchange is logged to the Block 16 audit trail with
   full provenance.
3. The Block 22 alignment gate is operational and a known-bad event is
   demonstrably rejected in a test.
4. Backup and recovery to the D-056 24-hour window has been demonstrated
   by a test restore, not merely configured.
5. Personality document and alignment rules document are loaded into Block 16
   and activated through the D-079 two-step mechanism.
6. The pre-launch checklist in the Block 23 source code specification is
   fully completed.

## Rationale
D-035 defined v0.1 scope but left "done" undefined. The six criteria are
derived from the Block 23 pre-launch checklist plus cross-block integrity
requirements not visible from the surface alone. All six must be true
simultaneously.

## Consequences
Rules out shipping v0.1 without a demonstrated test restore. Rules out
shipping v0.1 without the alignment gate operationally verified. Rules out
treating pre-launch checklist completion alone as sufficient.

## Related Decisions
D-035 (v0.1 scope), D-056 (24-hour backup window),
D-079 (system document activation), D-094 (v0.1 signed off).
