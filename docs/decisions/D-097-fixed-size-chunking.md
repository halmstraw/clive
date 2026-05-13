---
id: D-097
title: Fixed-size chunking 512 tokens; 50-token overlap; 50-token minimum
status: Accepted
date: 2026-05-01
blocks: Block 15 (Processing)
agents: Knowledge Agent
---

## Context
Block 15 must chunk ingested documents before embedding. Chunk size, overlap,
and minimum chunk size affect retrieval quality and embedding cost.

## Options Considered
A. Fixed-size chunking: 512 tokens, 50-token overlap, 50-token minimum (chosen)
   — simple, predictable, well-understood tradeoffs; consistent with D-023.
B. Semantic chunking (sentence or paragraph boundaries) — higher quality but
   more complex; not necessary at v0.1 scale.
C. Larger fixed-size chunks (1024+) — fewer embeddings but lower retrieval
   precision; more context per chunk but harder to cite sources.

## Decision
Block 15 uses fixed-size chunking with 512-token chunks, 50-token overlap
between adjacent chunks, and a 50-token minimum chunk size. Chunks below the
minimum are discarded (e.g. trailing document fragments).

## Rationale
512 tokens fits well within embedding model context limits. 50-token overlap
prevents context loss at chunk boundaries. Fixed-size chunking is simple and
predictable — consistent with D-023. Semantic chunking can be introduced in a
later version if retrieval quality requires it.

## Consequences
Rules out semantic chunking at v0.1. Rules out larger chunk sizes at v0.1.
Chunks below 50 tokens are discarded; very short documents may produce no
chunks and will be rejected.

## Related Decisions
D-096 (embedding model), D-098 (max ingest file size), D-023 (simplicity).
