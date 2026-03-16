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
| Generate task contracts | Conditional | Conductor / Human |
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
Pre-merge review is optional; post-merge review is mandatory.

| Step | Required | Actor |
|------|----------|-------|
| Create Linear issue | Yes | Human |
| Create branch | Yes | Human |
| Implement fix | Yes | Human / Builder |
| Verification (tests pass) | Yes | Verifier |
| Gate evaluation | Relaxed | Gate (minimal profile) |
| Create PR | Yes | Human / Orchestrator |
| Pre-merge review | Optional | Reviewer |
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

## Spec Hierarchy: Three Layers

Every change produces artifacts at up to three spec layers.  Not every
layer is required for every task.

| Layer | Artifact | Question it answers | Consumer |
|-------|----------|---------------------|----------|
| **L1: Spec** | `spec.md` | What to build? What behaviour must hold? | Humans, Gate |
| **L2: Contract** | `contract.md` | How to build safely? What to touch, what not to touch? | Coding agent |
| **L3: Test** | `test_*.py` | Is it done? Does the behaviour hold? | CI, Gate |

L1 is always required for Full tier.  L2 is conditional (see below).
L3 is always required for Full and Standard tiers.

## Task Contract Policy

A task contract (L2) constrains the coding agent's execution boundaries.
It is **not required for every task** — only for high-risk ones.

**When to write a contract:**

- The task modifies a file imported by 3+ other modules
- Multiple tasks in the same change modify the same file
- The function being changed has 10+ existing tests
- The task's Forbidden Paths would be longer than its Allowed Paths

**When to skip:**

- Pure new files (no regression surface)
- Documentation or configuration only
- Hotfix tier (speed over safety)

**Contract structure** (see `docs/architecture/spec-contract-integration.md`):

1. Intent — external result
2. Decisions — confirmed choices + open questions
3. Boundaries — allowed paths, forbidden paths, non-regression list
4. Completion Criteria — behaviours, new tests, regression checks
5. Verification Plan — commands to run, failure triage
6. Risk Notes — likely overreach points

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
1. Human discovers junk issues (e.g. SON-57, SON-58, ...) caused by a test bug
2. Human creates SON-XX in Linear (Bug label)
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
