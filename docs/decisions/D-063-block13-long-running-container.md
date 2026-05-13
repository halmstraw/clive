---
id: D-063
title: Block 13 runs as long-running containerised service; starts at boot
status: Accepted
date: 2026-05-01
blocks: Block 13 (Orchestrator), Block 27 (Infrastructure/IaC)
agents: Systems Agent, Infrastructure Agent
---

## Context
The in-process event bus (D-062) requires a persistent process. The runtime
model for Block 13 must be compatible with that requirement.

## Options Considered
A. Long-running container, starts at boot (chosen) — natural runtime for
   an in-process bus; consistent with D-062.
B. Serverless / function-per-event — requires externalising bus state;
   negates the simplicity of the in-process choice.

## Decision
Block 13 runs as a long-running containerised service. It starts at boot
and remains running. Single instance, no redundancy (D-023).

## Rationale
The in-process event bus (D-062) requires a persistent process to live in.
A long-running container is the natural and only coherent runtime for this
combination. Serverless invocation would require externalising bus state,
negating the simplicity of the in-process choice.

## Consequences
Rules out serverless / function-per-event runtime for Block 13. Rules out
any runtime that does not provide a persistent process for the in-process
bus.

## Related Decisions
D-062 (in-process event bus), D-023 (single instance),
D-064 (single cloud VM).
