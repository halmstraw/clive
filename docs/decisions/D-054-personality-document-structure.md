---
id: D-054
title: Personality document uses named sections written as prose instructions
status: Accepted
date: 2026-05-01
blocks: Block 1 (Personality), Block 16 (Storage), Block 8 (Query/RAG)
agents: Experience Agent (Block 1 content), Knowledge Agent (Block 16 storage)
---

## Context
The personality document encoding (D-039) was decided but the internal
structure of the document left open. Three structural options were considered.

## Options Considered
A. Single continuous unstructured block — hardest to update precisely;
   individual traits not independently editable.
B. Named sections with bullets — risks reading as a ruleset rather than
   a character; mechanical rather than intentional.
C. Named sections written as prose instructions (chosen) — diffable,
   reads as intent, precisely updatable.

## Decision
The personality document uses a hybrid structure: short named sections
written as prose instructions, not bullet lists.

## Rationale
Continuous text is hardest to update precisely. Named sections with bullets
risk reading as a ruleset. Prose sections give Block 16 something diffable
and the LLM something that reads as intent rather than constraint.

## Consequences
Rules out single continuous unstructured block. Rules out bullet-list
sections.

## Related Decisions
D-039 (personality encoding), D-048 (Block 1 as document not service),
D-049 (system document activation).
