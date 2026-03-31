# Program Reconciliation And Stability Acceptance Plan

> **Status note (2026-03-30):** Tranche S1 completed. Tranche S2 is now
> implemented as the canonical matrix plus updated operator guides. Tranche S3
> baseline automation for issue-start and mission/milestone-start is also
> landed. UI/exploratory automation and continuous reporting remain open.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reconcile program state after the large core-extraction refactor, sync docs and Linear to the code that actually shipped, and establish a repeatable stability-acceptance loop before new feature work resumes.

**Architecture:** Treat this as a first-class program epic, not cleanup. The work splits into two parallel seams: state reconciliation and stability acceptance. State reconciliation makes docs and Linear reflect the repo truth. Stability acceptance creates a durable automated acceptance harness across issue-start, milestone/mission-start, UI, and exploratory flows.

**Tech Stack:** Python 3.13, existing `LinearClient`, `runtime_core`, `decision_core`, `acceptance_core`, `acceptance_runtime`, FastAPI dashboard surfaces, shell-based e2e harnesses, pytest, Playwright/browser evidence paths.

---

## 1. Why This Is A Program Epic

The architecture work is now ahead of the management and validation layers.

Today the repo has:

- merged core extraction through Epics 1-7
- landed bounded `acceptance_runtime/`
- landed memory/evolution/contract linkage

But the system of record is not yet synchronized:

- some plan docs still describe Epic 4 runtime as deferred when bounded runtime is already landed
- Linear now needs a reconciliation pass for completed epics/issues and a new acceptance-stability epic
- no single durable acceptance matrix exists for issue-start, milestone/mission-start, UI, and exploratory paths

This epic fixes that.

## 2. Scope

### In scope

- reconcile program completion state in docs and Linear
- create a canonical stability acceptance matrix
- automate feature acceptance for major launch paths
- automate dashboard/UI acceptance for major surfaces
- automate exploratory acceptance runs where feasible
- continuously update acceptance status as failures are fixed or deferred

### Out of scope

- new product/runtime features unrelated to stability acceptance
- broad owner-merge work
- new orchestration abstractions outside acceptance/validation needs

## 3. Deliverables

### Deliverable A: Program reconciliation

- update top-level plan docs so they match shipped code
- mark completed epics/issues accurately
- create a new Linear epic for post-refactor stability acceptance
- attach the acceptance follow-up work to a visible Linear parent

### Deliverable B: Stability acceptance matrix

- define the canonical feature/UI/exploratory acceptance matrix
- identify what is already automated vs manual vs missing
- specify the command or harness entry point for each row

### Deliverable C: Automated acceptance harness

- issue-start e2e acceptance
- milestone/mission-start e2e acceptance
- dashboard/UI route acceptance
- exploratory acceptance smoke coverage
- persistent acceptance status outputs suitable for repeated execution

### Deliverable D: Continuous status reporting

- docs show latest acceptance status
- Linear child issues reflect current blockers and completion state
- the acceptance loop can be rerun without re-planning the entire program

## 4. Execution Tranches

### Tranche S1: Reconcile state

**Status:** Completed

**Files:**
- Modify: `docs/plans/2026-03-30-epic-4-7-program-plan.md`
- Modify: `docs/plans/2026-03-29-linear-ready-epic-mapping.md`
- Create: `docs/plans/2026-03-30-program-reconciliation-and-stability-acceptance.md`
- Create: `docs/plans/2026-03-30-stability-acceptance-matrix.md`

**Tasks:**
- confirm actual code/PR state for Epics 1-7
- rewrite stale plan language so bounded `acceptance_runtime` is treated as landed
- add explicit “current focus” section for stability acceptance
- create the Linear epic and child issue set for this work

### Tranche S2: Build the acceptance matrix

**Status:** Completed

**Files:**
- Create: `docs/plans/2026-03-30-stability-acceptance-matrix.md`
- Modify: `docs/agent-guides/run-pipeline.md`
- Modify: `docs/agent-guides/services.md`

**Tasks:**
- list major feature launch paths
- list major UI/dashboard surfaces
- list exploratory acceptance flows
- define pass/fail artifacts and owners for each row
- wire the canonical feature launch rows into agent/operator guides

### Tranche S3: Automate feature acceptance

**Status:** Baseline issue-start and mission/milestone-start harnesses completed

**Files:**
- Modify/Create under: `tests/e2e/`
- Modify/Create under: `src/spec_orch/services/`
- Modify/Create under: `tests/unit/` where harness adapters need coverage

**Tasks:**
- automate issue-start e2e
- automate mission/milestone-start e2e
- capture expected artifacts and pass/fail assertions
- materialize canonical smoke reports suitable for repeated operator review

### Tranche S4: Automate UI and exploratory acceptance

**Files:**
- Modify/Create under: `tests/e2e/`
- Modify/Create under: `src/spec_orch/dashboard/`
- Modify/Create under: `src/spec_orch/services/acceptance/`

**Tasks:**
- automate dashboard route acceptance
- automate post-run acceptance review surfaces
- add exploratory acceptance smoke coverage with bounded evidence assertions

### Tranche S5: Continuous reporting

**Files:**
- Modify/Create: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Optional helper code under: `src/spec_orch/services/` or `src/spec_orch/cli/`

**Tasks:**
- persist last-known acceptance run status
- expose rerunnable commands
- keep docs and Linear in sync with the current acceptance baseline

## 5. Initial Linear Breakdown

Create one new epic:

- `[Epic] Program Reconciliation and Stability Acceptance`

Create these initial child issues:

1. `Reconcile Epic 1-7 completion state across docs and Linear`
2. `Define canonical stability acceptance matrix`
3. `Automate issue-start acceptance e2e`
4. `Automate milestone and mission-start acceptance e2e`
5. `Automate dashboard feature and UI acceptance`
6. `Automate exploratory acceptance smoke flows`
7. `Add continuous acceptance status reporting`

## 6. Completion Gate

This epic should only be considered complete when:

- docs and Linear no longer disagree with shipped code
- the acceptance matrix exists and is current
- major launch paths are rerunnable through automated acceptance commands
- dashboard/UI acceptance has a repeatable harness
- exploratory acceptance has at least bounded smoke coverage
- acceptance status can be updated continuously without re-opening planning work
