---
id: D-075
title: GitHub Actions is the CI/CD pipeline tool for Block 28
status: Accepted
date: 2026-05-01
blocks: Block 28 (CI/CD), Block 27 (Infrastructure/IaC)
agents: Infrastructure Agent
---

## Context
D-041 (RepoRails) establishes the CLIVE repository on GitHub. The CI/CD
tool should follow from the repository hosting decision.

## Options Considered
A. GitHub Actions (chosen) — native to GitHub; no additional service;
   no separate credentials; well-understood by AI coding agents (D-009).
B. CircleCI, Jenkins, GitLab CI — additional service to configure and
   credential; no significant advantage given GitHub hosting.

## Decision
GitHub Actions is the CI/CD pipeline tool for Block 28.

## Rationale
The CLIVE repository is hosted on GitHub (D-041). GitHub Actions is the
natural pipeline tool — no additional service, no credentials to manage for
a separate CI platform, well-understood by AI coding agents, which is the
primary build mode (D-009).

## Consequences
Rules out CircleCI, Jenkins, GitLab CI, or any other CI/CD platform at v0.1
without a superseding decision.

## Related Decisions
D-041 (RepoRails, GitHub hosting), D-090 (self-hosted runner),
D-091 (Terraform in CI).
