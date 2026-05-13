---
id: D-006
title: Every destructive or irreversible action requires explicit human confirmation
status: Accepted
date: 2026-05-01
blocks: Block 9 (Action Layer), all blocks capable of irreversible action
agents: All agents — constrains all action-capable block designs
---

## Context
A capable AI system will inevitably be asked to take actions that cannot be
undone — deleting data, sending messages, making purchases. The cost of an
accidental irreversible action may be unrecoverable.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
Every destructive or irreversible action requires explicit human confirmation
before execution. Timeout results in rejection, never execution.

## Rationale
The cost of an unintended irreversible action may not be recoverable.
Requiring explicit confirmation is the only structural guarantee; policy
alone is not sufficient.

## Consequences
Rules out autonomous destructive actions of any kind. Rules out pre-approved
blanket authorisation for categories of irreversible action. Block 9 (Action
Layer) implements the confirmation gate for all such actions.

## Related Decisions
D-034 (variant promotion requires owner sign-off), D-049 (system document
activation two-step), D-079 (v0.1 system document activation mechanism).
