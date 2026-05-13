---
id: D-041
title: CLIVE repo uses RepoRails for AI-optimised repository structure
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD), Block 29 (Documentation),
        Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent, all agents (follow repo conventions)
---

## Context
AI-assisted development is the primary build mode for CLIVE. An ad-hoc
repository structure makes it harder for AI coding agents to navigate and
contribute effectively.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
The CLIVE code repository uses RepoRails to maintain AI-optimised repository
structure and conventions.

## Rationale
AI-assisted development is the primary build mode (D-009, D-018). RepoRails
structures the repository so that AI coding agents can navigate, understand,
and contribute with maximum effectiveness — consistent file layout,
conventions, and context files that reduce agent hallucination and improve
output quality.

## Consequences
Rules out ad-hoc repository structure. Rules out repository conventions
that are not declared and enforced. Rules out any repo layout that is not
loadable as coherent context by an AI agent.

## Related Decisions
D-009 (build model A), D-018 (agents stateless).
