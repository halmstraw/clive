---
id: D-068
title: Block 16 raw store uses S3-compatible object storage
status: Accepted
date: 2026-05-01
blocks: Block 16 (Storage), Block 14 (Ingestion), Block 27 (Infrastructure/IaC)
agents: Knowledge Agent, Infrastructure Agent
---

## Context
Raw ingested documents must be stored durably and independently from the
PostgreSQL instance. Binary content in a relational database is costly
and limits scale.

## Options Considered
A. S3-compatible object storage (chosen) — purpose-built for binary content;
   independently backupable; cheap at scale.
B. PostgreSQL large objects or bytea columns — costly; pollutes the database;
   limits scale.
C. Local filesystem — not independently backupable; not recoverable from IaC.

## Decision
Block 16's raw store uses S3-compatible object storage. Original ingested
documents are stored as blobs referenced by key. PostgreSQL holds the
metadata and key references; the object store holds the content.

## Rationale
Raw documents will grow unboundedly as ingestion runs. Object storage is
the correct abstraction for arbitrary binary content at any scale — cheap,
purpose-built for large files, and keeps binary content out of the
PostgreSQL instance. The nightly PostgreSQL snapshot (D-056) covers
structured data; the raw store is covered independently.

## Consequences
Rules out storing raw documents as PostgreSQL large objects or bytea columns.
Rules out local filesystem storage for raw documents. Rules out any raw store
approach that is not independently backupable from the PostgreSQL instance.

## Related Decisions
D-056 (24-hour backup window), D-069 (object store backup requirement),
D-089 (dedicated backup credentials).
