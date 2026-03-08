# SpecOrch System Design v0

## 1. Purpose

SpecOrch is an AI-native software delivery orchestration system for individuals and small teams. Its purpose is to let engineers spend most of their time defining tasks, boundaries, and acceptance criteria while controlled coding agents handle the bulk of implementation, verification, preview, and review.

The target outcome is not fully autonomous merge on day one. The target outcome is a reliable, auditable, and iterative delivery loop that can be trusted and improved over time.

## 2. Core Goals

SpecOrch is built around five fixed roles:

1. `Linear` is the task control plane.
2. `Obsidian` is the knowledge plane.
3. `Orchestrator` is the runtime coordination center.
4. `Codex`, `Claude`, and browser or device agents are the execution adapters.
5. `Spec` and `Gate` define completion and mergeability.

The primary system goal is to transform issue-driven work into isolated, spec-governed execution runs with clear validation, review, and acceptance checkpoints.

## 3. Design Principles

### 3.1 Separate Tasks from Knowledge

- `Linear` answers what should be done.
- `Obsidian` captures why it matters, what happened, and what was learned.

### 3.2 Separate Planning from Execution

- Humans define the task intent, boundaries, and acceptance standard.
- Agents execute implementation inside a controlled environment.

### 3.3 Move Review Earlier

- Humans should review the contract and intent before implementation.
- Machines should verify whether the contract was satisfied.
- Humans should spend final acceptance time on outcomes rather than rereading every diff.

### 3.4 One Issue, One Execution Context

- Each `Linear` issue maps to one isolated workspace.
- That workspace owns its branch, artifacts, logs, and environment.
- Multiple unrelated tasks must not share a mutable execution context.

### 3.5 Single Source of Truth per Domain

- Task status lives in `Linear`.
- Knowledge records live in `Obsidian Markdown`.
- Merge authority lives in `Gate`.

### 3.6 Agents Are Not Merge Authority

- Agents may report completion.
- Only `Gate` may classify a task as `Mergeable`.
- Human acceptance remains the final product decision.

## 4. Scope

### 4.1 In Scope for v0 and v1

The first working system should support:

1. Pulling issues from `Linear`.
2. Creating an isolated workspace per issue.
3. Generating or assembling `task.spec` and `progress.md`.
4. Routing implementation to `Codex`.
5. Routing review to `Claude`.
6. Running baseline verification:
   - install
   - lint
   - typecheck
   - unit and integration tests
   - build
7. Optionally running preview plus browser smoke or dogfood checks.
8. Writing results back to:
   - `Linear`
   - pull requests
   - local run records
9. Computing `Mergeable` through a gate engine.

### 4.2 Out of Scope for v1

The first version should explicitly avoid:

1. Multi-tenant SaaS concerns.
2. Automatic merge to main.
3. Deep cost governance.
4. Large device matrix support.
5. Large-scale distributed scheduling.
6. First-class support for every agent adapter on day one.
7. Fully autonomous requirements clarification.

## 5. Architecture Overview

SpecOrch consists of five planes.

### 5.1 Control Plane

`Linear` is the control plane.

Responsibilities:

- create and maintain projects, issues, priority, and state
- act as the task entrypoint and source of truth for workflow state
- trigger autonomous or assisted runs
- present high-level execution outcomes and acceptance status

### 5.2 Knowledge Plane

`Obsidian` is the knowledge plane.

Responsibilities:

- architecture decision records
- design documents
- debugging notes
- retrospectives
- work logs
- links to issues, commits, specs, and reports

### 5.3 Orchestration Plane

The orchestrator is the runtime controller. It may begin life as a local daemon or a lightweight service.

Responsibilities:

- watch or poll `Linear`
- assemble task context
- create execution workspaces
- route to agents
- manage retries, timeouts, and escalation
- aggregate verification and review output
- write state changes back out

### 5.4 Execution Plane

Execution is adapter-driven.

- `Codex` handles primary implementation work.
- `Claude` handles review and higher-order analysis.
- browser or device agents handle UI verification and dogfood checks.
- additional adapters may be added later behind a stable interface.

### 5.5 Spec and Gate Plane

This plane defines what done means and whether a task may advance.

Responsibilities:

- maintain task intent, decisions, boundaries, and completion criteria
- drive lifecycle validation
- produce structured verdicts and explain reports
- determine whether a task is `Mergeable`

## 6. Roles

### 6.1 Human Operator

The human operator creates and maintains issues, reviews specs, performs final acceptance, and handles escalations for ambiguous or high-risk work.

### 6.2 Planner or Spec Agent

The planner derives an initial spec from the issue and surrounding knowledge context. Default choice: `Claude`.

### 6.3 Builder Agent

The builder implements the task and attempts local verification. Default choice: `Codex`.

### 6.4 Reviewer Agent

The reviewer checks for spec sufficiency, boundary violations, architectural drift, and misaligned implementation. Default choice: `Claude`.

### 6.5 Verifier Agent

The verifier runs preview, smoke, and dogfood flows where needed. Default choice: `Playwright` or another browser or device executor.

### 6.6 Gate Engine

The gate engine aggregates results and issues the only mergeability verdict that matters to the workflow.

## 7. Lifecycle

Primary workflow:

```text
Backlog
-> Triaged
-> Spec Drafted
-> Spec Approved
-> In Progress
-> Self Verified
-> Review Pending
-> Review Changes Requested
-> Preview Ready
-> Acceptance Pending
-> Mergeable
-> Merged
```

Exception states:

```text
Blocked
Needs Human Input
Verification Failed
Environment Failed
Abandoned
```

### 7.1 State Intent

- `Backlog`: new issue, not yet classified for execution.
- `Triaged`: execution mode, risk, repository, and spec need are decided.
- `Spec Drafted`: planner generated the initial task contract.
- `Spec Approved`: contract is accepted and workspace may be created.
- `In Progress`: builder is actively implementing.
- `Self Verified`: builder passed the baseline checks.
- `Review Pending`: reviewer is evaluating spec, diff, and summary.
- `Review Changes Requested`: reviewer found issues that require another build cycle.
- `Preview Ready`: optional UI checkpoint after deploy or preview creation.
- `Acceptance Pending`: human sees the concise explain report, preview link, and residual risks.
- `Mergeable`: all gate conditions are satisfied.
- `Merged`: target branch integration is complete.

## 8. Core Objects

### 8.1 Linear Issue

Recommended fields:

- `issue_id`
- `title`
- `project`
- `priority`
- `labels`
- `auto_mode`
- `risk_level`
- `repo`
- `acceptance_owner`
- `state`
- `linked_pr`
- `linked_spec`
- `linked_obsidian_notes`

### 8.2 Task Spec

Each task should have one `task.spec` with the following sections:

- `Intent`
- `Context`
- `Decisions`
- `Boundaries`
- `Completion Criteria`
- `Test Plan`
- `Related Links`

The spec is the contract between the operator and the execution system.

### 8.3 Progress File

Each task should have one `progress.md` capturing:

- status
- current step
- completed work
- remaining work
- verification
- review notes
- preview
- blockers
- next action

### 8.4 Workflow Configuration

Repository-level workflow rules belong in documents such as:

- `AGENTS.md`
- `WORKFLOW.md`
- `project.spec`

These define constraints, risk policy, review expectations, and preview behavior.

### 8.5 Explain Report

The explain report is the human-facing summary for acceptance. At minimum it should contain:

- task intent
- changed file scope
- verification results
- reviewer verdict
- preview URL
- known limitations
- mergeable status

## 9. Workspace Model

Each `Linear` issue must run in an isolated execution context.

### 9.1 Requirements

- separate directory
- separate branch or worktree
- separate run log
- separate environment injection
- separate artifacts, including spec, progress, and reports

### 9.2 v1 Default Strategy

Use:

- git worktrees
- local sandbox directories

Future versions may add containers, VMs, or remote runners, but isolation by worktree is sufficient for the first loop.

## 10. Agent Routing

### 10.1 Builder Routing

Default builder: `Codex`

Suitable task types:

- feature implementation
- bug fixes
- bounded refactors

### 10.2 Reviewer Routing

Default reviewer: `Claude`

Suitable task types:

- diff review
- spec review
- architecture consistency review
- higher-risk reasoning checks

### 10.3 Verifier Routing

Default verifier: `Playwright` or another browser executor

Suitable task types:

- page load validation
- critical path smoke
- preview dogfood

### 10.4 Extensibility

The orchestrator must support future adapters such as `Cursor`, `Amp`, `OpenCode`, or `Antigravity` without rewiring core orchestration logic.

## 11. Adapter Interface

Every agent adapter should implement a minimal common interface:

- `can_handle(task_type)`
- `prepare(context_bundle)`
- `run(task_bundle)`
- `collect_artifacts()`
- `get_verdict()`
- `cleanup()`

Suggested task types:

- `spec_authoring`
- `implementation`
- `review`
- `ui_verification`
- `documentation`
- `research`

This keeps the orchestrator coupled to capabilities, not to a single agent product.

## 12. Verification and Gate

### 12.1 Baseline Verification

All code tasks should run:

- install
- lint
- typecheck
- unit or integration tests
- build

### 12.2 Review Verification

The reviewer should emit a structured verdict:

- `pass`
- `changes_requested`
- `uncertain`

### 12.3 Preview Verification

For web tasks, preview checks may include:

- preview deploy
- smoke test
- dogfood pass

### 12.4 Gate Checks

The gate engine should verify:

1. approved `task.spec` exists
2. changed files stay inside `Boundaries`
3. baseline verification passed
4. reviewer verdict passed
5. preview or dogfood passed when required
6. human acceptance completed

Only then may the task enter `Mergeable`.

## 13. Mergeable Definition

A task is `Mergeable` only when all of the following are true:

1. `task.spec` exists
2. `task.spec` is approved
3. all changed files stay inside the declared boundaries
4. lint, typecheck, tests, and build pass
5. reviewer verdict is `pass`
6. preview and smoke checks pass when the task requires them
7. human acceptance is complete

An agent's claim of completion is informational only. It is never the merge decision.

## 14. Write-Back

### 14.1 Linear

SpecOrch should write back:

- state transitions
- execution summary
- PR links
- preview links
- explain report links or excerpts

### 14.2 Obsidian

SpecOrch should write back:

- work logs
- design change records
- retrospectives
- notable failures and resolutions

### 14.3 Pull Requests

SpecOrch should generate:

- spec summary
- verification results
- review summary
- preview URL
- known limitations

## 15. Audit

Each run must preserve enough detail for reconstruction and review.

Minimum audit fields:

- `issue_id`
- `workspace_id`
- branch or worktree
- participating agents
- start and end timestamps
- verification results
- review verdict
- state transition history
- failure reason
- retry count

Future versions may add cost and throughput metrics, but those should not block v1.

## 16. v1 Modules

The first usable system should include:

1. `Issue Watcher`
2. `Context Builder`
3. `Workspace Manager`
4. `Agent Router`
5. `Run Controller`
6. `Verification Aggregator`
7. `State Sync`
8. `Audit Store`

## 17. v1 Technical Strategy

### 17.1 Orchestrator Runtime

Start with a single local or deployable daemon plus repository configuration. Use polling first and add event-driven hooks later.

### 17.2 Workspace Isolation

Start with git worktrees and local directory isolation.

### 17.3 Spec and Gate

Start with lightweight artifacts:

- `task.spec`
- `progress.md`
- `verify.sh`
- `explain.md` or `report.json`

### 17.4 Review

Start with a structured review template emitted by `Claude`, not a fully autonomous arbitration layer.

### 17.5 Preview

Start with:

- `Vercel` preview
- `Playwright` smoke tests

## 18. Non-Functional Requirements

- Reliability: one task failure must not pollute another workspace.
- Auditability: every critical action and verdict must be reconstructable.
- Extensibility: adapters must be pluggable.
- Controllability: operators must be able to pause, take over, or rerun.
- Simplicity: v1 should optimize for a closed loop, not for abstract completeness.

## 19. Main Risks

### 19.1 Fragmented State

Mitigation: keep task workflow truth in `Linear`.

### 19.2 Knowledge Lost in Chat or PR Threads

Mitigation: require important decisions and debugging history to be written into `Obsidian`.

### 19.3 Builder and Reviewer Role Collapse

Mitigation: keep implementation and review responsibilities separated across adapters.

### 19.4 Over-Automation

Mitigation: preserve assisted mode and mandatory human acceptance.

### 19.5 Adapter Scope Creep

Mitigation: stabilize the first version around `Codex`, `Claude`, and browser verification only.

## 20. Success Criteria for v1

The first version is successful if it can:

1. pull a task from `Linear`
2. create an isolated workspace
3. generate spec and progress artifacts
4. dispatch `Codex` for at least one class of implementation task
5. dispatch `Claude` for structured review
6. execute and aggregate baseline verification
7. provide preview and smoke results for web tasks
8. write results back to `Linear` and pull requests
9. compute `Mergeable`
10. complete at least one real end-to-end run on a live repository

## 21. Evolution Path

### 21.1 v1.1

- better explain reports
- better retry policy
- finer-grained risk policy

### 21.2 v1.2

- automatic Obsidian worklog generation
- stronger spec lint and lifecycle checks
- richer review templates

### 21.3 v2

- more adapters
- device-based verification
- multi-repository workflows
- richer workflow policy
- dedicated orchestration dashboard

## 22. Summary

SpecOrch is not just another coding bot. It is a delivery control system for AI-assisted software work.

- `Linear` decides what work exists.
- `Obsidian` records why the work matters and what was learned.
- `Orchestrator` controls who does what and under which constraints.
- agents perform the actual execution.
- `Spec` and `Gate` decide whether the work is actually done and safe to merge.

That separation is the defining idea of the system and should remain stable as the implementation evolves.
