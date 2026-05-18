# D-158 — Sonar Quality Gate enforced via branch protection on main

| Field | Value |
|---|---|
| ID | D-158 |
| Title | Sonar Quality Gate enforced via branch protection on main |
| Status | Accepted |
| Date | 2026-05-18 |
| Blocks | Block 28 (CI/CD), Block 27 (Infrastructure/IaC) |
| Recorded by | Architect |

## Context

Two gaps allowed Sonar issues to reach production undetected:

1. `sonar.qualitygate.wait` was not set in `sonar-project.properties`. The
   SonarCloud scan step uploaded results but never caused the CI job to fail,
   even when the Quality Gate was red. Sonar was reporting-only.

2. `deploy.yml` triggers on `push: branches: [main]` independently of `ci.yml`.
   Even when CI failed, the deploy pipeline proceeded unblocked.

The owner identified this pattern and requested that code — including code pushed
by Claude Code — cannot reach main without the Sonar Quality Gate passing.

## Decision

Enforce the Sonar Quality Gate as a hard gate on main via two changes:

**1. `sonar-project.properties`**
Add `sonar.qualitygate.wait=true`. This causes the `sonarcloud-github-action`
step to poll the SonarCloud API until the Quality Gate result is available and
fail the CI job if the gate is red. Without this property the step is
reporting-only.

**2. GitHub branch protection on main**
Configure the main branch with the following rules, enforced on admins:
- Require a pull request before merging (0 required approvals — single-owner
  project; the gate is CI, not human review)
- Require the `CI / Test` status check to pass before merging
- Require branches to be up to date before merging
- Do not allow bypassing these settings (enforce on admins)

Direct pushes to main are rejected by GitHub. All code — including Claude Code
commits — must land via a PR that has a green `CI / Test` job. That job includes
the Sonar scan, which now fails on a red Quality Gate.

## Workflow change

Claude Code's development workflow changes from direct push to:
1. Push commits to a feature branch
2. Create a PR targeting main
3. CI runs on the PR (already configured — `ci.yml` triggers on
   `pull_request: branches: [main]`)
4. When `CI / Test` is green (Sonar Quality Gate passes), merge the PR
5. Merge triggers `deploy.yml` as before

`deploy.yml` does not need to change — by the time code is on main,
CI has already passed.

## Alternatives considered

**A — Deploy-gate only (workflow_run).** Deploy blocked if CI fails, but code
can still be pushed directly to main. Rejected: broken code can still land on
main even if deploy doesn't fire.

**C — Both (branch protection + workflow_run).** Redundant once branch
protection is in place. Not adopted.

## Consequences

- No code reaches main without a passing Sonar Quality Gate.
- Direct pushes to main are rejected for all actors including repo admins.
- Claude Code must use PRs for all commits.
- `deploy.yml` is unchanged — it continues to trigger on push to main,
  which can now only happen via merged PR.
