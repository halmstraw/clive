---
id: D-095
title: CI integration tests use containerised PostgreSQL; production never tested against
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD), Block 16 (Storage)
agents: Infrastructure Agent, Knowledge Agent
---

## Context
Integration tests require a real PostgreSQL instance. Options are to test
against a containerised instance spun up per CI run, the production database,
or a shared staging database.

## Options Considered
A. Containerised PostgreSQL per CI run (chosen) — isolated; no production risk;
   each run starts from a known clean state.
B. Test against production database — unacceptable; tests could corrupt live
   data.
C. Shared staging database — requires additional infrastructure; introduces
   state between runs.

## Decision
CI integration tests use a containerised PostgreSQL instance spun up per run.
Production is never tested against. Each run starts from a clean state. The
container matches the production PostgreSQL version.

## Rationale
Isolation and reproducibility. Tests that share state with production or
between runs are unreliable. A per-run container is cheap in CI and eliminates
the class of failure caused by shared database state.

## Consequences
Rules out testing against production. Rules out a shared staging database at
v0.1. Requires CI workflow to define a PostgreSQL service container.

## Related Decisions
D-058 (PostgreSQL), D-075 (GitHub Actions), D-090 (self-hosted runner).
