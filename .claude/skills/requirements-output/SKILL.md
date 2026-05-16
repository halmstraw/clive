---
name: requirements-output
description: >
  Use when producing, reviewing, or verifying requirements for a CLIVE block.
  Triggers on: "requirements for block N", "deepen requirements", "document
  block requirements", "is this block done", "requirements complete", or
  any session where a specialist agent is producing deliverables for a block.
  Defines what a complete block requirements document looks like and what
  "done" means, so /goal conditions are verifiable and agent outputs are
  consistent.
---

# Requirements Output

## Purpose

Each specialist agent produces requirements documents for its block group.
Without a standard format, documents from different agents are incompatible,
`/goal` completion conditions are hard to verify, and the Architect cannot
review cross-block consistency efficiently.

This skill defines the standard. All block requirements documents must
conform to it.


---

## Where Requirements Documents Live

```
docs/requirements/block-N-[short-name].md
```

Examples:
- `docs/requirements/block-8-query-rag.md`
- `docs/requirements/block-16-storage.md`
- `docs/requirements/block-9-action-layer.md`

One file per block. Do not combine multiple blocks in one document.

---

## Standard Document Structure

Every block requirements document must contain these sections in this order.
All sections are required. Do not add sections not listed here without
flagging to the Architect first.

### 1. Header

```markdown
# Block N — [Block Name] — Requirements
Agent: [Agent Name]
Status: Draft / Under Review / Complete
Last updated: [date]
Decisions recorded: [list of D-NNN IDs that shaped this document]
```

### 2. Purpose (2–4 sentences)

What this block exists to do. Written in terms of what CLIVE achieves
because this block exists, not how the block works. No technology choices.

### 3. Responsibilities

A numbered list of what this block must do. Each item is a testable
requirement — it can be evaluated as met or not met.

Format each item as:
`The block must [verb] [what] [under what conditions/constraints].`

Avoid: "The block should", "The block may", "The block could".
Requirements are musts.

### 4. Must Not Do

A numbered list of explicit exclusions. Things that are out of scope,
forbidden, or belong to another block.

This section prevents scope creep and makes cross-block boundaries explicit.

### 5. Interfaces (Event Bus)

All inter-block communication expressed using the event-schema skill format.

Two subsections:
- **Events Emitted** — events this block sends to Block 13
- **Events Consumed** — events this block receives from Block 13

If no events are defined yet, write "TBD — event schema not yet specified"
and flag for the next session.

If a consumer or emitter belongs to another agent's block group, include
a CROSS-BLOCK DEPENDENCY FLAG (see event-schema skill).

### 6. Constraints

The non-negotiable design constraints that apply to this block. These come
from DECISIONS.md and CLAUDE.md. Cite the decision ID where one exists.

Format: `[D-NNN] [Constraint statement]`

At minimum, include whichever of these apply:
- D-003: Event bus — no direct block-to-block calls
- D-004: Alignment boundary — route to Architect
- D-005: Personality survives the Reaper (Block 1 only)
- D-006: Confirmation gate for destructive actions
- D-002: No technology choices in requirements

### 7. Open Questions

Questions that arose during requirements deepening that are not yet resolved.
Each open question should become a decision ask (use the record-decision skill).

Format each as:
```
OQ-N: [Question]
Status: Raised as D-NNN ask / Pending / Resolved as D-NNN
```

If all open questions are resolved, write "None — all questions resolved
into decisions."

### 8. Assumptions

Things assumed to be true that are not yet recorded as decisions. If an
assumption turns out to be wrong, it will affect these requirements.

Each assumption should be reviewed and either confirmed as a decision
or flagged for the owner.

### 9. Done Criteria

The explicit list of conditions that must be true for this block's
requirements to be considered complete.

Standard done criteria (all must be met):
- [ ] All responsibilities are stated as testable musts
- [ ] Must Not Do section defines block boundaries clearly
- [ ] All inter-block interfaces expressed as events in event-schema format
- [ ] All cross-block dependencies flagged
- [ ] All constraints cited with decision IDs
- [ ] No technology choices made (no named databases, platforms, frameworks)
- [ ] All open questions either resolved into decisions or raised as asks
- [ ] Assumptions listed and reviewed
- [ ] Document reviewed by Architect for cross-block consistency
- [ ] Status set to Complete in header

---

## What "Complete" Means

A block's requirements are complete when:
1. The document exists at the correct path
2. All nine sections are present and filled
3. All done criteria are checked
4. Status in the header is "Complete"
5. The Architect has confirmed no cross-block conflicts

A `/goal` condition for requirements completion:

```
/goal docs/requirements/block-N-[name].md exists, contains all nine
required sections per the requirements-output skill, has status Complete
in the header, and no open questions remain unresolved. Max 20 turns.
```

---

## What Requirements Are Not

- Not technology choices (no database names, no framework names)
- Not implementation plans (no "we will use X to do Y")
- Not architecture diagrams (those come later)
- Not design documents (requirements say what; design says how)

If a requirements document contains technology choices, flag it immediately
and request revision before the session continues.
