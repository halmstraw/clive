---
name: fetch-decisions
description: >
  Use at the start of every session, and whenever DECISIONS.md needs to be
  verified as current. Triggers on: "fetch decisions", "load decisions",
  "check decisions", "session start", or any instruction that requires
  current decision state before proceeding. Covers fetching from Notion,
  confirming the highest decision ID, handling unreachable Notion, and
  reporting what is under review.
---

# Fetch Decisions

## Purpose

DECISIONS.md is the authoritative decision log for CLIVE. It lives in Notion.
No local copy is authoritative. Every session must start with a fresh fetch.

## Notion URL

https://www.notion.so/3574837a97d381568100cd1370c68264

## Procedure

Follow these steps in order. Do not skip any step.

### Step 1 — Fetch

Use WebFetch to retrieve the live DECISIONS.md from the Notion URL above.

If Notion is unreachable:
- Stop immediately
- Report: "Notion unreachable. Cannot confirm current decision state.
  Please provide a local copy explicitly and confirm it is current,
  or restore connectivity before proceeding."
- Do not proceed with any design, requirements, or implementation work

### Step 2 — Confirm highest decision ID

Identify the highest decision ID in the fetched document (format: D-NNN).
Report it explicitly:

> "DECISIONS.md loaded. Highest decision ID: D-NNN."

If the document is empty or contains no decision entries:
- Report this as unusual and ask the owner to confirm before proceeding

### Step 3 — Flag open items

Scan for any entries marked "Under Review" or with no recorded resolution.
Report each one:

> "Open items requiring attention this session:
> - D-NNN: [decision title] — Under Review"

If none: "No open items."

### Step 4 — Confirm and proceed

State that decisions are loaded and the session may proceed.
Do not restate the full decision log unless the owner asks for it.

## What This Skill Does Not Do

- Does not write to DECISIONS.md — only the Architect does that
- Does not interpret decisions — reports what is there
- Does not proceed if Notion is unreachable — stops and waits

## Example Output

```
DECISIONS.md loaded. Highest decision ID: D-041.

Open items:
- D-038: Block 8 retrieval confidence model — Under Review

Session may proceed.
```
