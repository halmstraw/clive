---
name: record-decision
description: >
  Use when raising a decision, direction, or approval ask to the owner.
  Triggers on: any moment an agent needs the owner to choose between options,
  approve a recommendation, or set a direction. Enforces the standard CLIVE
  decision protocol format. Also use when flagging that a session outcome
  needs recording in DECISIONS.md.
---

# Record Decision

## Purpose

Every significant ask to the owner follows the same format. One ask per
message. No exceptions. This skill enforces that format and reminds agents
when a session outcome should be recorded in DECISIONS.md.

---

## Part 1 — Raising an Ask

Use this exact format. Fill every field. Do not omit fields or add new ones.

```
AGENT: [Agent Name]
TYPE: [Decision / Direction / Approval]
CONTEXT: [One sentence — what you were working on when this arose.]
THE ASK: [The specific question or choice, stated plainly.]
OPTIONS:
  A. [Concrete option — specific enough to act on]
  B. [Concrete option — specific enough to act on]
  C. [Concrete option, if needed — maximum three]
RECOMMENDATION: [Which option and one sentence why.]
IF NO RESPONSE: Stop and wait.
BLOCKS AFFECTED: [Which CLIVE blocks this touches — block numbers and names.]
```

### Type definitions

**Decision** — Two or more real options exist. The owner chooses.
Use when reasonable people could disagree about the right path.

**Direction** — The agent is stuck, outside its remit, or facing a question
that requires owner judgment to set the path. Use when the agent cannot
determine the options itself.

**Approval** — The agent has a clear recommendation and needs sign-off
before proceeding. Use when the path is obvious but the action is significant
enough to require explicit owner confirmation.

### Rules for options

- Each option must be concrete and specific enough to act on immediately
- Options must be mutually exclusive — picking A must preclude B
- Maximum three options. If you have more, consolidate
- Do not pad with a "do nothing" option unless doing nothing is genuinely
  one of the valid choices

### Rules for asks

- Never ask open-ended questions ("What do you think about...?")
- Never bundle asks — one ask per message, highest priority first
- Never proceed past a decision point without an owner response
- If the owner does not respond: stop and wait

---

## Part 2 — Flagging for DECISIONS.md

When a session produces a significant decision — whether through the ask
format above or through conversation — flag it for recording before the
session ends.

Use this format:

```
DECISIONS.md FLAG
Decision reached: [one sentence describing the decision]
Context: [what prompted it]
Resolution: [what was decided]
Blocks affected: [block numbers and names]
Recorded by: Architect [or: needs Architect to record]
```

### What counts as significant

Record in DECISIONS.md when:
- A design choice is made between two or more real alternatives
- A constraint is established that will affect future work
- A block interface or event schema is finalised
- A technology choice is made (when that phase arrives)
- An agent is activated or deactivated
- The alignment constitution is modified (owner only)
- A block's requirements are marked complete

Do not record: exploratory discussion without resolution, minor clarifications,
questions that were asked but not answered yet.

### Who writes to DECISIONS.md

Only the Architect writes to DECISIONS.md. Specialists flag what needs
recording. The Architect writes the entry.

---

## Example Ask

```
AGENT: Intelligence Agent
TYPE: Decision
CONTEXT: Deepening Block 9 confirmation gate requirements for watch surface.
THE ASK: How should timeout be handled when a pending action awaits
         confirmation on the watch surface and the watch goes offline?
OPTIONS:
  A. Timeout equals rejection — action is cancelled, owner notified on
     next available surface when it reconnects.
  B. Action remains pending indefinitely — no timeout — until confirmed
     or explicitly cancelled by the owner.
  C. Configurable timeout per action type, set by the owner in Block 19
     (Configuration/Admin), defaulting to rejection.
RECOMMENDATION: A. Aligns with D-006 (timeout equals rejection, never
     execution) and avoids indefinitely pending destructive actions.
IF NO RESPONSE: Stop and wait.
BLOCKS AFFECTED: Block 9 (Action Layer), Block 2 (Multi-Surface),
     Block 5 (Sync/State Layer).
```

## Example DECISIONS.md Flag

```
DECISIONS.md FLAG
Decision reached: Watch surface timeout equals rejection for Block 9 gate.
Context: Deepening Block 9 requirements for limited-capability surfaces.
Resolution: Option A — timeout cancels action, owner notified on reconnect.
Blocks affected: Block 9, Block 2, Block 5.
Recorded by: Needs Architect to record.
```
