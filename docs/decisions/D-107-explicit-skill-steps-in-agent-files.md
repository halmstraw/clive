---
id: D-107
title: Explicit skill workflow steps added to all agent files
status: Accepted
date: 2026-05-14
blocks: Block 29
agents: All agents
---

## Context
Skills in `.claude/skills/` are described in CLAUDE.md as "auto-discovered"
by Claude Code. In practice this is soft enforcement: the model infers when
a skill applies rather than executing a named, mandatory step. During the
v0.3 scope session, the Architect correctly used record-decision Part 1 (the
ask format) but skipped record-decision Part 2 (the DECISIONS.md FLAG block)
before writing ADR files. No structural mechanism caught the gap.

## Options Considered
A. Add explicit skill steps to all seven agent files — skill usage becomes
   a named obligation in each agent's own prompt.
B. Narrower scope — apply only to the Architect file first, extend later.
C. Accept soft enforcement; rely on owner review.

## Decision
Option A. All seven agent files in `.claude/agents/` are updated to include
explicit, named skill workflow steps:

**All agents:**
- Session start: run fetch-decisions sequence before acting on any instruction.
- Before any ask to the owner: follow record-decision Part 1 (ask format).
- Before any DECISIONS.md write: output record-decision Part 2 (FLAG block) first.

**Systems Agent, Knowledge Agent, Intelligence Agent (additionally):**
- When designing inter-block interfaces: follow event-schema skill.

**Intelligence Agent, Knowledge Agent (additionally):**
- When producing requirements documents: follow requirements-output skill.

## Rationale
Converts a model-inference requirement into a named workflow step visible in
the agent's own prompt. Removes the "I didn't realise it applied" failure mode.
Does not eliminate all risk of non-compliance but makes deviation visible in
the transcript and gives every agent an explicit checklist.

## Consequences
All agent files are updated in a single pass. Future agent files must include
the same explicit skill steps from creation. Skill additions require a
corresponding DECISIONS.md entry and update to relevant agent files.

## Related Decisions
D-008 (decisions recorded before implementation), D-010 (standard decision
protocol), D-041 (RepoRails repo structure).
