---
name: fetch-decisions
description: >
  Use at the start of every session, and whenever DECISIONS.md needs to be
  verified as current. Triggers on: "fetch decisions", "load decisions",
  "check decisions", "session start", or any instruction that requires
  current decision state before proceeding. Reads the local DECISIONS.md
  from the repo root, confirms the highest decision ID, and reports any
  entries under review.
---

# Fetch Decisions

## Purpose

DECISIONS.md at the repo root is the authoritative decision log for CLIVE.
The full ADR files live in `docs/decisions/`. Git history is the audit trail.
Notion is a read-only view — do not treat it as authoritative.

## Procedure

Follow these steps in order. Do not skip any step.

### Step 1 — Read

Use the Read tool to load `DECISIONS.md` from the repo root.

If the file is missing or unreadable:
- Stop immediately
- Report: "DECISIONS.md not found. Cannot confirm current decision state.
  The repo may be in an inconsistent state — please investigate before
  proceeding."
- Do not proceed with any design, requirements, or implementation work

### Step 2 — Confirm highest decision ID

Identify the highest decision ID in the index (format: D-NNN).
Report it explicitly:

> "DECISIONS.md loaded. Highest decision ID: D-NNN."

If the file is empty or contains no decision entries, report this as unusual
and ask the owner to confirm before proceeding.

### Step 3 — Flag open items

Scan for any entries with status `Under Review` or `Superseded by D-NNN`
that are relevant to this session's work. Report each one:

> "Open items relevant to this session:
> - D-NNN: [decision title] — Under Review"

If none: "No open items."

### Step 4 — Load relevant ADR files

For session work that touches specific blocks, read the individual ADR files
from `docs/decisions/D-NNN-*.md` for those blocks using the Blocks column
in the index. Do not load all 100+ files — only those relevant to the work.

### Step 5 — Confirm and proceed

State that decisions are loaded and the session may proceed.
Do not restate the full decision log unless the owner asks for it.

## What This Skill Does Not Do

- Does not write to DECISIONS.md — only the Architect does that
- Does not interpret decisions — reports what is there
- Does not fall back to Notion — if DECISIONS.md is missing, stops and waits

## Example Output

```
DECISIONS.md loaded. Highest decision ID: D-102.

Open items relevant to this session: none.

Session may proceed.
```
