---
id: D-096
title: Block 15 uses OpenAI text-embedding-3-small via LiteLLM; 1536 dimensions
status: Accepted
date: 2026-05-01
blocks: Block 15 (Processing), Block 16 (Storage), Block 8 (Query/RAG)
agents: Knowledge Agent, Intelligence Agent
---

## Context
Block 15 (Processing) must produce vector embeddings for ingested documents.
A model and dimension count must be chosen. The choice affects storage size,
query performance, and retrieval quality.

## Options Considered
A. OpenAI text-embedding-3-small via LiteLLM, 1536 dimensions (chosen) —
   strong quality-to-cost ratio; well-supported; consistent with LiteLLM
   abstraction (D-057).
B. OpenAI text-embedding-3-large — higher cost; marginal quality gain for v0.1
   scale; inconsistent with D-023 (simplicity).
C. Local embedding model — additional infrastructure; not necessary at v0.1.

## Decision
Block 15 uses `text-embedding-3-small` via LiteLLM for all document embeddings.
Vector dimension is 1536. pgvector stores embeddings in a `vector(1536)` column.
All retrieval in Block 8 operates against 1536-dimension vectors.

## Rationale
Strong quality-to-cost ratio at v0.1 scale. LiteLLM abstraction (D-057) means
the model can be swapped later without changing Block 15's interface. 1536
dimensions gives adequate retrieval quality without excessive storage cost.

## Consequences
Rules out local embedding models at v0.1. Rules out text-embedding-3-large
at v0.1. Fixes the pgvector column dimension at 1536; changing this requires
re-embedding all documents and a schema migration.

## Related Decisions
D-057 (LiteLLM), D-058 (PostgreSQL + pgvector), D-023 (simplicity).
