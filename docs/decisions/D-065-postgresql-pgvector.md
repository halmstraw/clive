---
id: D-065
title: Block 16 search index uses PostgreSQL with pgvector extension
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 8 (Query/RAG), Block 13 (Orchestrator),
        Block 27 (Infrastructure/IaC)
agents: Knowledge Agent, Intelligence Agent (Block 8), Infrastructure Agent
---

## Context
Block 8 requires hybrid retrieval — keyword search and vector similarity.
The search infrastructure must fit within a single-VM deployment and
integrate with the relational store.

## Options Considered
A. PostgreSQL + pgvector (chosen) — simplest; one service; hybrid retrieval
   via FTS and pgvector; consistent with D-023 and D-064.
B. Dedicated vector database (Qdrant, Weaviate) — separate service to
   operate; premature at v0.1 query volume.

## Decision
Block 16's search index is implemented using PostgreSQL with the pgvector
extension. Keyword search via PostgreSQL full-text search, vector similarity
via pgvector, semantic reranking in application code.

## Rationale
At v0.1, query volume is low. Combining the search index with the relational
store in one service is the simplest approach consistent with D-023 and D-064
(single VM). pgvector satisfies Block 8's hybrid retrieval interface
requirement.

## Consequences
Rules out dedicated vector database (Qdrant, Weaviate, or similar) at v0.1.
Rules out separate search infrastructure from the relational store at v0.1.

## Related Decisions
D-066 (single PostgreSQL instance for state store),
D-096 (embedding dimensions — vector(1536)).
