---
id: D-047
title: Block 8 confidence signal is retrieval quality only; no LLM self-assessment
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 25 (Observability)
agents: Intelligence Agent, Infrastructure Agent (Block 25)
---

## Context
Block 8 must signal confidence in its responses. Two approaches: retrieval
quality metrics (measurable) or LLM self-assessment (unreliable).

## Options Considered
A. Retrieval quality only (chosen) — grounded in measurable data; honest.
B. LLM self-assessment — notoriously unreliable; adds prompt complexity
   with false precision.

## Decision
Block 8's confidence signal is retrieval quality only at v0.1 — number of
chunks returned, highest relevance score, and whether any chunks met a
minimum relevance threshold. Block 8 does not attempt LLM self-assessment.

## Rationale
Retrieval quality is the only confidence signal grounded in measurable data.
LLM self-assessment is notoriously unreliable and adds prompt complexity
with false precision. No relevant retrieval results is an honest
low-confidence signal.

## Consequences
Rules out LLM self-assessed confidence at v0.1. Rules out confidence signals
not grounded in measurable retrieval data.

## Related Decisions
D-043 (orchestrator-mediated retrieval), D-044 (context allocation).
