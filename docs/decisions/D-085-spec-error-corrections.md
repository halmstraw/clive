---
id: D-085
title: Two spec errors corrected during v0.1 scaffold review; recorded for audit
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG)
agents: Intelligence Agent
---

## Context
Two errors were identified during v0.1 scaffold review that required
correction before the scaffold could function. Both are unambiguous spec
errors, not design decisions.

## Options Considered
Not applicable — these are corrections to errors, not choices between options.

## Decision
Two spec errors identified during v0.1 scaffold review are recorded for audit
completeness:

(1) pyproject.toml build backend: `setuptools.backends.legacy:build` is not
a valid module path; corrected to `setuptools.build_meta` by Claude Code.

(2) Test calibration in Block 8: `test_history_truncation` used 50 × 500-char
messages (~6,250 tokens) against a 98,000-token budget, meaning truncation
never triggered; corrected to 100 × 10,000-char messages by Claude Code.

Both fixes are unambiguous corrections to spec errors, not design decisions.

## Rationale
Not applicable — both are corrections to non-functional specifications.

## Consequences
Rules out treating either correction as a design change requiring owner
decision. Rules out reverting either fix.

## Related Decisions
None.
