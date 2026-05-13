---
id: D-083
title: CLIVE infrastructure accounts registered under cliveai@proton.me
status: Accepted
date: 2026-05-01
blocks: Block 27 (Infrastructure/IaC), Block 28 (CI/CD), Block 23 (Security)
agents: Infrastructure Agent
---

## Context
CLIVE infrastructure accounts (Hetzner, GitHub, Telegram bot registration)
must be registered under some email address. Using the owner's personal
email conflates CLIVE's operational identity with the owner's personal
accounts.

## Options Considered
A. Dedicated Proton Mail address (chosen) — privacy by design; Swiss
   jurisdiction; clean separation from personal accounts.
B. Existing personal email — conflates CLIVE infrastructure with personal
   accounts; alerts and spend mixed with personal mail.

## Decision
CLIVE infrastructure accounts are registered under a dedicated Proton Mail
address created solely for CLIVE: cliveai@proton.me. This address is used
for Hetzner, GitHub, Telegram bot registration, and any other service account
created for CLIVE's infrastructure. It is not used for personal
correspondence.

Condition: The T10 owner-incapacitation contingency must include access
credentials or recovery path for this account. Loss of access means loss of
access to all CLIVE infrastructure accounts. Recovery PDF stored in a secure
physical location separate from the password manager.

## Rationale
Separating CLIVE's infrastructure identity from the owner's personal accounts
keeps spend, alerts, and service communications auditable and distinct.
Proton Mail chosen for privacy by design, no ad-based scanning, Swiss
jurisdiction consistent with D-070 (European infrastructure), and clean
separation from existing personal accounts.

## Consequences
Rules out using any existing personal email account for CLIVE infrastructure
registrations. Does not constitute formation of a legal entity — that remains
gated behind D-036 preconditions.

## Related Decisions
D-070 (Hetzner), D-036 (Business Layer preconditions).
