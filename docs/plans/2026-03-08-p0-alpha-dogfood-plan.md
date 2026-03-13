# SpecOrch P0-Alpha Dogfood Plan

> **Historical Document (2026-03-08).** This was the first dogfood plan.
> The decision to use `codex app-server` was reversed in favour of
> `codex exec --json`. The daemon architecture described here has since
> been significantly expanded (readiness triage, review loop, merge
> readiness, state persistence). See [README](../../README.md) for the
> current implementation.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move SpecOrch from a fixture-driven local prototype to a real dogfoodable orchestrator that pulls work from Linear, creates issue workspaces, runs Codex coding turns, writes results back, and keeps progressing through an event loop without manual shell babysitting.

**Architecture:** Keep the current local-first Python orchestrator, but replace the fixture issue entrypoint with a minimal Linear ingress path and a daemon-style run loop. Continue using git worktrees, file-backed artifacts, deterministic gate evaluation, and the existing Codex harness builder. Review remains a dummy pass for this phase so coding flow can become the primary dogfood loop.

**Tech Stack:** Python 3.13, Typer CLI, pytest, git worktree, file-backed JSON/Markdown artifacts, Linear API via `httpx`, Codex `app-server` harness, optional PR comment sync via GitHub API.

## Review Decisions Incorporated

The 2026-03-08 project review changed this plan in two important ways:

- **Adopt now**
  - extract `IssueSource` before Linear ingress lands
  - extract `BuilderAdapter` protocol before more adapters accumulate
  - reduce `RunController` duplication with a shared finalize path
- **Adopt later**
  - explicit `ReportSchema`
  - dynamic verification step model
  - config/policy files
- **Do not switch now**
  - keep `codex app-server` as the primary builder transport for dogfooding
  - treat `codex exec` as a fallback or future simplification path, not an immediate rewrite

Rationale:

- `IssueSource` / `BuilderAdapter` / `RunController` refactors directly unblock the next phase and reduce coupling before Linear work starts.
- `codex exec` is simpler, but the current product goal still benefits from thread/turn semantics and richer harness observability.

## Scope

This phase intentionally focuses on these four priorities:

1. Real Linear ingress
2. Linear / PR write-back
3. Daemon / queue / rerun
4. Acceptance summary unification

This phase explicitly defers:

- real Claude review adapter
- Playwright/browser verifier
- Obsidian sync
- shared observability stack

## Success Criteria

SpecOrch reaches `P0-alpha` when all of these are true:

- A real Linear issue can be pulled into SpecOrch without using `fixtures/issues/*.json`
- SpecOrch can create or reuse an issue worktree from that Linear issue
- SpecOrch can run Codex builder + verification from that issue and write back status
- The orchestrator can continue polling or draining a queue without interactive babysitting
- The final human-facing acceptance summary is coherent without cross-reading multiple artifacts

## Dogfood Rules

- New orchestration features should be implemented through SpecOrch issue runs whenever the current system can support the path.
- This chat should prefer orchestration, debugging, acceptance, and policy decisions over directly editing feature code.
- Direct hand-edits are still allowed for bootstrap or recovery work when the dogfood path itself is blocked.

## Backlog Order

### P0-0: Internal Refactor for Linear Readiness

**Outcome:** Reduce the minimum architectural coupling before real external issue sources arrive.

**Why first:** The review is correct that adding Linear directly into the current `RunController` / fixture loading path would make the next phase messier and harder to test.

**Target behavior:**

- `RunController` no longer owns fixture loading directly
- builder execution depends on a builder interface instead of a concrete class
- finalization logic is centralized enough to avoid three near-duplicate paths

**Dogfood issue ideas:**

- `SPC-R1`: Extract `IssueSource` with `FixtureIssueSource`
- `SPC-R2`: Introduce `BuilderAdapter` protocol and route Codex through it
- `SPC-R3`: Extract shared run finalization path from run/review/accept
- `SPC-R4`: Evaluate `codex exec` as a documented fallback path without replacing harness primary

### P0-1: Real Linear Ingress

**Outcome:** Replace fixture-only issue loading with a real Linear-backed issue source.

**Why second:** Without this, SpecOrch is still a demo harness instead of a real task entrypoint, but it should land after the minimal refactors above.

**Target behavior:**

- `run-issue` can accept a real Linear issue ID
- SpecOrch can fetch title, description, state, labels, and project metadata from Linear
- The orchestrator can map a Linear issue into the local `Issue` domain object
- Fixture loading remains available as a fallback for isolated tests

**Dogfood issue ideas:**

- `SPC-L1`: Add Linear client and auth config
- `SPC-L2`: Load issue context from Linear API instead of fixture JSON
- `SPC-L3`: Convert Linear issue fields into `Issue` domain model
- `SPC-L4`: Support fallback between fixture mode and Linear mode

### P0-3: Linear / PR Write-Back

**Outcome:** SpecOrch writes run status and summaries back to the systems humans already read.

**Why second:** Once issues come from Linear, results must return there or the workflow still leaks into local-only artifacts.

**Target behavior:**

- Write issue state summary back to Linear after each run/review/acceptance transition
- Write key URLs / artifacts / blocked conditions into the issue
- Optionally write a compact PR comment if a PR URL or PR number is available

**Dogfood issue ideas:**

- `SPC-W1`: Add Linear write-back client
- `SPC-W2`: Sync run summary to Linear issue comments or custom fields
- `SPC-W3`: Sync gate result and blocked conditions to Linear state/comment
- `SPC-W4`: Add minimal PR comment writer with explain/report summary

### P0-4: Daemon / Queue / Rerun

**Outcome:** SpecOrch can keep operating without a human manually invoking each issue run.

**Why third:** This is the step that turns the system into an actual orchestrator instead of a command wrapper.

**Target behavior:**

- A long-running process can poll Linear or drain a local queue
- It can claim one issue, run it, record outcome, and move on
- It can rerun a specific issue safely
- It can avoid duplicate concurrent execution of the same issue

**Dogfood issue ideas:**

- `SPC-D1`: Add queue abstraction and run-claim semantics
- `SPC-D2`: Add `spec-orch daemon` command
- `SPC-D3`: Add rerun command by issue ID / run ID
- `SPC-D4`: Add simple lockfile or run-claim protection per issue

### P1-1 promoted into P0-alpha tail: Acceptance Summary Unification

**Outcome:** Humans can accept or reject with one artifact view, not multiple JSON/Markdown hops.

**Why now:** Once ingress and write-back exist, acceptance becomes the primary human touchpoint.

**Target behavior:**

- A single acceptance-facing summary contains:
  - intent
  - changed files
  - verification result
  - builder contract compliance
  - review verdict
  - blocked conditions
  - mergeability
- The same summary can be sent to Linear / PR / local explain artifact

**Dogfood issue ideas:**

- `SPC-A1`: Define unified acceptance summary schema
- `SPC-A2`: Generate acceptance summary artifact from existing reports
- `SPC-A3`: Reuse the same summary in Linear write-back and PR comment output

## Suggested Execution Sequence

1. Extract `IssueSource`, `BuilderAdapter`, and shared finalization paths
2. Implement a minimal Linear client and auth loading
3. Swap issue loading from fixture-only to fixture-or-Linear
4. Add Linear write-back for run status
5. Add daemon command with polling and rerun support
6. Unify acceptance summary once the loop is event-driven

## Practical Notes

- Keep dummy review for this whole phase. Do not spend time on real Claude review yet.
- Keep Playwright verification deferred unless a dogfood issue specifically depends on it.
- Prefer small issues that can be run by the current system, even if one bootstrap issue still requires direct edits.
- Update README after each milestone so the documented workflow matches reality.
- If `codex exec` is explored, do it as an alternate adapter experiment, not as a forced replacement of the current harness path.
