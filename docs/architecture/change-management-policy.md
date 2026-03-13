# Change Management Policy

Every code change to SpecOrch must follow a tracked, auditable process.
This document defines three tiers of change, the minimum required steps
for each, and the hard rules that apply to all tiers.

## Hard Rules (All Tiers)

1. **No direct push to main.**  Every change goes through a branch and
   a pull request.  This is enforced by GitHub branch protection
   (`enforce_admins: true`).
2. **Every change has a Linear issue.**  No exceptions.  The issue
   provides traceability: who found it, when it was fixed, why it was
   fixed that way.  Issues without a Linear link cannot be merged.
3. **Every PR links to its Linear issue.**  Use `Closes SON-XX` in the
   PR body so the Linear-GitHub App auto-closes the issue on merge.

## Tier Definitions

### Full (New Features, Architecture Changes)

The complete EODF pipeline.  Use when the change introduces new
capabilities, modifies public interfaces, or affects system architecture.

| Step | Required | Actor |
|------|----------|-------|
| Create Linear issue | Yes | Human / Daemon |
| Discuss / brainstorm | Yes | Planner |
| Freeze → spec.md | Yes | Human |
| Mission approve | Yes | Human |
| Generate execution plan | Yes | Planner |
| Promote to Linear issues | Yes | Orchestrator |
| Execute work packets | Yes | Builder (Codex) |
| Verification | Yes | Verifier |
| Gate evaluation | Yes | Gate |
| Create PR | Yes | Orchestrator |
| PR review | Yes | Reviewer |
| Merge | Yes | Gate / Human |
| Retrospective | Recommended | Orchestrator |

**Linear labels:** `task` (on work packets), `epic` (on parent)

### Standard (Bug Fixes, Small Improvements)

A shortened pipeline for changes that don't require spec design or
multi-packet execution.  The fix is well-understood and scoped.

| Step | Required | Actor |
|------|----------|-------|
| Create Linear issue | Yes | Human / Daemon |
| Create branch | Yes | Human / Daemon |
| Implement fix | Yes | Human / Builder (Codex) |
| Verification | Yes | Verifier |
| Gate evaluation | Yes | Gate |
| Create PR | Yes | Human / Orchestrator |
| PR review | Yes | Reviewer |
| Merge | Yes | Gate / Human |

**Skipped steps:** discuss, freeze, plan, promote, retrospective

**Linear labels:** `Bug` or `Improvement` + `task`

**Daemon behaviour:** The daemon already supports this tier.  A `Bug`
or `Improvement` issue in `Ready` state is picked up, built, verified,
gated, and PR'd — exactly like a single work packet, without requiring
a plan.json or mission.

### Hotfix (Production Blockers, Security Issues)

The fastest path for urgent fixes where delay is unacceptable.
Review can happen after merge if necessary.

| Step | Required | Actor |
|------|----------|-------|
| Create Linear issue | Yes | Human |
| Create branch | Yes | Human |
| Implement fix | Yes | Human / Builder |
| Verification (tests pass) | Yes | Verifier |
| Gate evaluation | Relaxed | Gate (minimal profile) |
| Create PR | Yes | Human / Orchestrator |
| PR review | Post-merge OK | Reviewer |
| Merge | Yes | Human |
| Post-merge review | Yes | Reviewer |

**Skipped steps:** discuss, freeze, plan, promote

**Linear labels:** `hotfix` + `task`

**Daemon behaviour (future):** When the daemon sees a `hotfix` label,
it will prioritise the issue, skip readiness triage, and use the
`minimal` gate profile.  This is not yet implemented — hotfixes are
currently handled manually.

## Decision Matrix

| Question | Full | Standard | Hotfix |
|----------|------|----------|--------|
| New user-facing feature? | Yes | — | — |
| Architecture or interface change? | Yes | — | — |
| Bug fix with clear scope? | — | Yes | — |
| Small refactor or improvement? | — | Yes | — |
| Production outage or security? | — | — | Yes |
| Needs spec review before coding? | Yes | No | No |
| Needs execution plan? | Yes | No | No |
| Pre-merge review required? | Yes | Yes | Optional |
| Post-merge review required? | No | No | Yes |
| Can daemon automate end-to-end? | Yes | Yes | Future |

## Branch Protection Settings

Applied to `main` via GitHub API:

| Setting | Value |
|---------|-------|
| Require pull request | Yes |
| Required approving reviews | 0 (bot review sufficient) |
| Dismiss stale reviews | No |
| Enforce for admins | Yes |
| Allow force push | No |
| Allow branch deletion | No |

## Examples

### Standard: Fix a test that creates real API calls

```
1. Human discovers SON-57~70 junk issues caused by a test bug
2. Human creates SON-71 in Linear (Bug label)
3. Human/Agent creates branch: fix/promote-test-side-effect
4. Agent fixes the test, runs verification
5. Agent creates PR linking SON-71
6. Reviewer bots review
7. Human merges → SON-71 auto-closes
```

### Hotfix: Fix a security vulnerability

```
1. Human creates SON-XX in Linear (hotfix label)
2. Human creates branch: hotfix/cve-2026-xxxxx
3. Human fixes the vulnerability
4. Runs tests to confirm no regression
5. Creates PR → merges immediately
6. Post-merge: reviewer bots review, retrospective filed
```
