# Block N — [Block Name] — Requirements

Agent: [Agent Name]
Status: Draft
Last updated: [YYYY-MM-DD]
Decisions recorded: [D-NNN, D-NNN — list decisions that shaped this document]

---

## Purpose

[2–4 sentences. What CLIVE achieves because this block exists.
No technology choices. No implementation detail.]

---

## Responsibilities

The block must:

1. [Verb + what + under what conditions/constraints]
2. [Verb + what + under what conditions/constraints]
3. [Continue as needed]

---

## Must Not Do

1. [Explicit exclusion or scope boundary]
2. [Explicit exclusion or scope boundary]
3. [Continue as needed]

---

## Interfaces (Event Bus)

*All inter-block communication expressed as events through Block 13.
Use the event-schema skill format. No direct block-to-block calls.*

### Events Emitted

```
EVENT: [EVENT_NAME]
  Emitted by:   Block N — [This Block]
  Consumed by:  Block N — [Block Name]
  Trigger:      [What causes this event]
  Payload:      [field, field, field]
  On failure:   [What happens if routing or consumption fails]
  Notes:        [Constraints, sequencing, open questions]
```

### Events Consumed

```
EVENT: [EVENT_NAME]
  Emitted by:   Block N — [Other Block]
  Consumed by:  Block N — [This Block]
  Trigger:      [What causes this event]
  Payload:      [field, field, field]
  On failure:   [What happens if routing or consumption fails]
  Notes:        [Constraints, sequencing, open questions]
```

### Cross-Block Dependency Flags

```
CROSS-BLOCK DEPENDENCY FLAG
Event: [EVENT_NAME]
Emitted by: Block N ([this block group])
Consumed by: Block M ([different agent's block group])
Flag for: [Agent name] to confirm consumption requirements
Status: Pending cross-agent review
```

---

## Constraints

[D-003] No direct block-to-block calls. All inter-block communication
routes through Block 13 via events.

[D-00N] [Additional constraint from DECISIONS.md]

[Add all constraints that apply to this block. Cite decision ID.]

---

## Open Questions

OQ-1: [Question]
Status: [Raised as D-NNN ask / Pending / Resolved as D-NNN]

OQ-2: [Question]
Status: [Raised as D-NNN ask / Pending / Resolved as D-NNN]

---

## Assumptions

1. [Something assumed to be true that affects these requirements]
2. [Something assumed to be true that affects these requirements]

---

## Done Criteria

- [ ] All responsibilities stated as testable musts
- [ ] Must Not Do section defines block boundaries clearly
- [ ] All inter-block interfaces expressed as events in event-schema format
- [ ] All cross-block dependencies flagged
- [ ] All constraints cited with decision IDs
- [ ] No technology choices made
- [ ] All open questions resolved into decisions or raised as asks
- [ ] Assumptions listed and reviewed
- [ ] Document reviewed by Architect for cross-block consistency
- [ ] Status set to Complete in header
