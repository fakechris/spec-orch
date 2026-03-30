# Acceptance-Integrated Program Rebaseline

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebase the architecture program so `Acceptance Judgment and Calibration` becomes an explicit program-level Epic, aligned with `runtime_core` and `decision_core`, instead of remaining a parallel side program or being scattered across later epics.

**Architecture:** The repo now has two large lines of work that can no longer be planned independently: core extraction in `llm_planner_orch`, and acceptance/judgment expansion in `codexharness`. The correct merge is not to let acceptance define a second runtime seam. The correct merge is to keep core extraction first, then insert acceptance judgment as the first major consumer of `runtime_core` and `decision_core`, before memory/evolution/surface cleanup proceed.

**Tech Stack:** Python 3.13, Linear epic/issue planning, current `src/spec_orch` package layout, acceptance harness docs and fixtures, shared execution semantics planning docs.

---

## 1. Decision

The 6-epic program is no longer the canonical planning shape.

The canonical program order is now:

1. `Epic 1: Shared Execution Semantics`
2. `Epic 2: Runtime Core Extraction`
3. `Epic 3: Decision Core Extraction`
4. `Epic 4: Acceptance Judgment and Calibration`
5. `Epic 5: Memory and Learning Linkage`
6. `Epic 6: Evolution and Policy Promotion Linkage`
7. `Epic 7: Contract Core Extraction and Surface Cleanup`

This replaces the previous order where memory/evolution/contract work followed directly after `Decision Core Extraction`.

## 2. Why The Program Had To Change

The `codexharness` worktree is already pushing acceptance beyond a thin evaluator:

- acceptance routing policy
- exploratory vs replay vs verification semantics
- candidate-finding ontology
- disposition and review states
- comparative calibration and fixture graduation
- surface-pack thinking for dashboard/operator-console dogfood

Those are too large and too cross-cutting to stay:

- hidden inside acceptance-specific service changes
- scattered under decision/memory/dashboard epics
- or planned as if they can land before core seams exist

At the same time, our current extraction work is explicitly trying to create:

- `runtime_core`
- `decision_core`
- shared execution and supervision primitives

If these lines proceed independently, the repo will almost certainly grow:

- one ontology for execution/decision cores
- another ontology for acceptance judgment/disposition
- duplicate review state carriers
- duplicate persistence seams

So the correct move is to make acceptance judgment the first named consumer of the extracted cores.

## 3. New Canonical Dependency Shape

### Epics 1-3 remain foundational

- `Shared Execution Semantics` defines the shared execution language
- `Runtime Core Extraction` gives that language a visible package boundary
- `Decision Core Extraction` gives supervision/review/intervention a visible package boundary

### Epic 4 becomes the first major consumer

`Acceptance Judgment and Calibration` depends on Epics 1-3 and pressure-tests them.

It should own:

- acceptance judgment model
- acceptance routing policy
- candidate-finding schema
- dashboard/operator-console surface pack v1
- comparative calibration harness
- candidate-to-fixture graduation loop

It should not define a parallel runtime core or decision core.

### Epics 5-7 move later

- `Memory and Learning Linkage` must ingest reviewed acceptance judgments, candidate outcomes, and graduation signals
- `Evolution and Policy Promotion Linkage` must consume reviewed acceptance evidence and promotion/dismissal outcomes
- `Contract Core Extraction and Surface Cleanup` should happen after those seams are stable enough not to churn surfaces immediately

## 4. Canonical Issue Insertions

The new Epic 4 should contain these issues:

1. `Define acceptance judgment model`
2. `Define acceptance routing policy`
3. `Define candidate-finding object model and review SOP`
4. `Add decision-core-compatible disposition seam`
5. `Define dashboard surface pack v1`
6. `Add comparative calibration harness`
7. `Add candidate-to-fixture graduation loop`

These come from:

- [`2026-03-29-acceptance-judgment-linear-integration.md`](./2026-03-29-acceptance-judgment-linear-integration.md)
- [`2026-03-29-acceptance-judgment-and-core-extraction-alignment.md`](./2026-03-29-acceptance-judgment-and-core-extraction-alignment.md)
- retained `codexharness` draft materials listed in the retention document

## 5. What Becomes Historical Rather Than Canonical

The following documents remain useful, but their 6-epic ordering is now historical baseline, not canonical program truth:

- [`2026-03-29-full-epic-and-issue-breakdown.md`](./2026-03-29-full-epic-and-issue-breakdown.md)
- [`2026-03-29-linear-ready-epic-mapping.md`](./2026-03-29-linear-ready-epic-mapping.md)

Until they are rewritten, they should be read together with this document and the acceptance integration docs above.

## 6. What Must Not Happen

Do not:

- let acceptance judgment land as a broad rewrite on old `services/` seams first
- let `round_orchestrator.py` become the permanent ontology owner for judgment/disposition
- let memory/evolution plan around acceptance as if it were only dashboard polish
- import `codexharness` acceptance models as repo-wide core truth without first mapping them to `runtime_core` / `decision_core`

## 7. Immediate Execution Consequences

### Planning

All future epic/issue planning should use the 7-epic order above.

### Linear

Linear should be updated to:

- add `[Epic] Acceptance Judgment and Calibration`
- create 7 issue cards under that epic
- adjust the dependency language for memory/evolution/contract epics so they now depend on acceptance judgment

### Retention

`codexharness` must not continue as the planning source of truth, but it does contain draft assets that must be preserved for later migration and decomposition.

See:

- [`2026-03-29-codexharness-retention-and-migration.md`](./2026-03-29-codexharness-retention-and-migration.md)

## 8. Bottom Line

The merged program shape is now:

- extraction first
- acceptance judgment second
- memory/evolution/contract afterward

That keeps `llm_planner_orch` as the planning source of truth while still preserving and absorbing the genuinely valuable acceptance/judgment work emerging in `codexharness`.
