---
id: D-039
title: Personality encoded as versioned constitutional document plus system prompt content
status: Accepted
date: 2026-05-01
blocks: Block 1 (Personality), Block 21 (Evolution Engine),
        Block 22 (Alignment Layer), Block 28 (CI/CD)
agents: Experience Agent (Block 1), Systems Agent (Block 21),
        Architect (Block 22), Infrastructure Agent (Block 28)
---

## Context
D-005 mandates that personality survives the Reaper but left the encoding
mechanism open. Three options were considered: fine-tuned model weights,
document-and-prompt, or a layered hybrid.

## Options Considered
A. Fine-tuned model weights — opaque, expensive to update, locks personality
   to a specific model generation.
B. Versioned constitutional document plus system prompt content (chosen) —
   satisfies D-005, consistent with D-002 and D-018, owner-readable,
   versionable through standard means.
C. Layered hybrid — adds structure before there is evidence it is needed.

## Decision
Personality (Block 1) is encoded as a versioned constitutional document plus
system prompt content, loaded into every relevant context window from the
central store. Personality lives in data, not in model weights.

## Rationale
Document-and-prompt encoding satisfies D-005, is consistent with D-002 (no
model lock-in), D-018 (state in central store), is owner-readable, and is
versionable through standard means.

## Consequences
Rules out fine-tuned model encoding of personality in v1. Rules out
personality state held inside any agent process or model weights. Rules out
personality definition that is not loadable from the central store.

## Related Decisions
D-005 (personality survives Reaper), D-048 (Block 1 as document not
service), D-054 (personality document structure).
