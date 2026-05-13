---
id: D-014
title: Transient Bootstrap Agent produces Architect prompt and specialist template then is retired
status: Accepted
date: 2026-05-01
blocks: System-wide
agents: Architect (recipient of Bootstrap Agent output)
---

## Context
The Architect cannot self-author its own system prompt without circular
dependency. An external agent is needed to bootstrap the prompt, but that
agent should not persist beyond its purpose.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
A transient Bootstrap Agent produces the Architect system prompt and
specialist instantiation template, then is retired.

## Rationale
Not explicitly recorded in original entry.

## Consequences
Rules out the Architect self-authoring its own prompt. Rules out the
Bootstrap Agent taking any ongoing role in the build.

## Related Decisions
D-009 (build model A), D-013 (specialist activation),
D-020 (system prompts delivered as single copyable code block).
