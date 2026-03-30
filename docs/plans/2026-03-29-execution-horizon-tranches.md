# Execution Horizon Tranches

> **Status 2026-03-30:** `Epic 1` is now materially complete. The execution-horizon document remains useful as historical sequencing context, but the active PR boundary and stop-condition review are captured in [`2026-03-30-epic-1-validation-and-pr-cut.md`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/docs/plans/2026-03-30-epic-1-validation-and-pr-cut.md).

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the 7-epic program into a near-term execution horizon that can run in Linear even though the team currently has no configured cycle objects.

**Architecture:** The program is too large to mark entirely `Ready` without losing sequencing discipline. Because the Linear team currently has workflow states but no cycle configuration, the correct short-term move is to define explicit execution tranches and reflect only the first tranche in `Ready`. Later tranches remain `Backlog` until their predecessors are materially complete.

**Tech Stack:** Linear states (`Backlog`, `Ready`, `In Progress`, `In Review`, `Done`), canonical 7-epic mapping, first-week tranche plan, Python 3.13 architecture program.

---

## 1. Current Constraint

The `SON` team currently has workflow states but no cycle objects configured.

That means the execution plan should use:

- explicit tranche planning in docs
- `Ready` for the current execution horizon
- `Backlog` for all later work

This is intentional. It is better than faking cycle semantics in issue text.

## 2. Tranche Rule

Only issues that can legitimately enter active engineering flow without reopening architectural ordering should be moved to `Ready`.

Everything else stays in `Backlog` until:

- predecessor tranche outcomes are verified
- the next seam is actually ready to open

## 3. Tranche A: Semantic Foundation

These are the first issues that should be marked `Ready` now:

- `E1-I1` `Add shared execution semantic models`
- `E1-I2` `Add read-side normalizers for issue and mission artifacts`
- `E1-I3` `Migrate read-side consumers to normalized execution reads`

### Why this tranche is first

Because it establishes the minimum shared execution language and read path before:

- dual-write churn
- writer cutover
- runtime-core package extraction

### Expected outcome

- issue and mission artifacts can be read through the same semantic layer
- dashboard / analytics / context consumers stop relying only on owner-local interpretations

## 4. Tranche B: Dual-Write and Cutover Readiness

These remain `Backlog` until Tranche A is materially complete:

- `E1-I4` `Add issue-path dual-write for normalized execution payloads`
- `E1-I5` `Add mission leaf dual-write for normalized execution payloads`
- `E1-I6` `Add mission round dual-write for normalized supervision payloads`
- `E1-I7` `Cut readers over to normalized execution preference`
- `E1-I8` `Cut canonical writes over to normalized execution payloads with bridge retention`
- `E1-I9` `Validate shared execution semantics rollout and stop conditions`
- `E2-I1` `Create runtime-core package skeleton`

### Why this tranche is second

Because it closes Phase 1 properly and creates the real handoff into `runtime_core`.

## 5. Tranche C: Runtime and Decision Bootstrap

These remain `Backlog` until Tranche B is materially complete:

- `E2-I2` through `E2-I9`
- `E3-I1` through `E3-I4`

### Why this tranche is third

Because it opens the first visible package seams:

- `runtime_core`
- `decision_core`

and gets mission supervision onto the first shared decision seam.

## 6. Acceptance, Memory, Evolution, and Contract Work

The following epics stay in `Backlog` for now:

- `Epic 4: Acceptance Judgment and Calibration`
- `Epic 5: Memory and Learning Linkage`
- `Epic 6: Evolution and Policy Promotion Linkage`
- `Epic 7: Contract Core Extraction and Surface Cleanup`

This does **not** mean they are unimportant.

It means:

- their program shape is now fixed
- their issues exist in Linear
- but they are not the immediate engineering horizon

## 7. State Policy

Current policy:

- Tranche A issues -> `Ready`
- everything else -> `Backlog` unless already intentionally moved by a human

Future policy:

- when Tranche A is materially complete, move Tranche B into `Ready`
- when Tranche B is materially complete, move Tranche C into `Ready`

## 8. Bottom Line

Without cycles configured, the repo should use:

- one canonical program tree
- one explicit execution-horizon document
- `Ready` as the current-horizon signal

That keeps the execution lane narrow without losing the larger 7-epic architecture program.
