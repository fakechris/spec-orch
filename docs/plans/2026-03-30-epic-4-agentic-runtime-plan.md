# Epic 4 Agentic Runtime Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the deferred ACPX-inspired Epic 4 runtime layer: explicit agentic graphs, stepwise prompt reveal, and per-step artifact execution.

**Architecture:** Keep graph structure, step contracts, loop/gate policy, and artifact persistence in code. Keep judgment reasoning, local exploration, and evidence interpretation in step-scoped prompts. The runtime owns control flow; prompts own bounded reasoning inside each step.

**Tech Stack:** Python 3.13, existing `acceptance_core`, `decision_core`, `runtime_core`, file-backed artifacts, dashboard surfaces.

**Current Status:** Tasks 1-6 baseline landed, plus tuned graph-family
expansion and fixture-seed linkage. The repo now has a bounded
`acceptance_runtime/` layer, step-scoped prompts, per-step artifacts, a graph
runner, and a first integration path through `round_orchestrator` and the
acceptance dashboard surface. Remaining work is graph-family expansion,
stronger loop/gate tuning, and deeper calibration/dashboard observability.
Step artifacts and graph traces now also feed the fixture-graduation audit
trail, fixture-candidate seed generation, and reviewed acceptance memory
provenance, so graph execution is no longer isolated to dashboard observability
alone.

## 1. Design Position

This plan does **not** turn Epic 4 back into a mega-prompt system.

It also does **not** require a general-purpose LangGraph-style platform first.

Instead, it introduces a bounded `acceptance_runtime/` layer for Epic 4 that:

- selects a graph profile from routing output
- executes named steps in a fixed graph
- reveals only the current step prompt to the LLM
- persists a structured artifact for each step
- evaluates loop/gate conditions in code
- emits graph-level observability that calibration can compare later

## 2. Split Of Responsibility

### Code-owned

Must live in runtime code, not prompt text:

- graph profile registry
- step ordering
- loop and gate placement
- budget enforcement
- step input/output schema
- artifact persistence paths
- compare overlay wiring
- graph-level observability
- transition rules from `observation` to `candidate_finding`

### Prompt-owned

Must remain in prompt scope:

- local reasoning for the current step
- evidence interpretation within step boundaries
- candidate wording / review summary generation
- bounded UX critique inside the active surface pack

### Why

If graph shape lives in prompt text, then:

- workflow tuning is untestable
- step provenance is unreliable
- compare drift becomes heuristic only
- calibration cannot distinguish model drift from orchestration drift

## 3. Runtime Shape

Introduce:

- `src/spec_orch/acceptance_runtime/graph_models.py`
- `src/spec_orch/acceptance_runtime/graph_registry.py`
- `src/spec_orch/acceptance_runtime/step_executor.py`
- `src/spec_orch/acceptance_runtime/artifacts.py`
- `src/spec_orch/acceptance_runtime/runner.py`
- `src/spec_orch/acceptance_runtime/prompts.py`

Core objects:

- `AcceptanceGraphProfileDefinition`
- `AcceptanceGraphStep`
- `AcceptanceStepInput`
- `AcceptanceStepResult`
- `AcceptanceGraphRun`
- `AcceptanceGraphRunSummary`

## 4. First Graph Profiles

Start with three bounded profiles only:

1. `verify_contract_graph`
   - steps:
     - `contract_brief`
     - `route_replay`
     - `assert_contract`
     - `summarize_judgment`

2. `baseline_replay_graph`
   - steps:
     - `baseline_brief`
     - `route_replay`
     - `compare_evidence`
     - `summarize_judgment`

3. `tuned_exploratory_graph`
   - steps:
     - `surface_scan`
     - `guided_probe`
     - `candidate_review`
     - `summarize_judgment`

`recon_probe_graph` should be the conservative fallback graph, not a free-form mode.

## 5. Stepwise Prompt Reveal

Each step gets:

- graph-level metadata
- only the current step instruction
- only the artifact subset needed for that step
- only the prior step outputs explicitly declared as inputs

Do **not** send the whole graph prompt every time.

Prompt composition should be:

- `system`: role + safety/budget rules
- `developer`: step contract and expected JSON shape
- `user`: current target/evidence slice

## 6. Per-Step Artifacts

Persist each step as a structured artifact:

- `graph_run.json`
- `steps/<n>-<step_key>.json`
- `steps/<n>-<step_key>.md` when natural-language review text matters

Each step artifact must include:

- `step_key`
- `graph_profile`
- `inputs`
- `outputs`
- `decision`
- `next_transition`
- `warnings`
- `timing`

These artifacts become:

- dashboard observability inputs
- calibration harness comparison inputs
- candidate-finding provenance inputs

## 7. Loop And Gate Policy

Loops and gates are code-owned.

Initial rules:

- `guided_probe` may loop up to a bounded budget
- `candidate_review` may only run if a prior step emitted reviewable observations
- `summarize_judgment` only runs after graph exit conditions are satisfied
- high-risk/mutation-sensitive routes cannot activate exploratory loops

## 8. Integration Points

### Acceptance routing

`acceptance_core.routing` continues to choose:

- `base_run_mode`
- `graph_profile`
- `budget_profile`
- `compare_overlay`

### Round orchestrator

`round_orchestrator` should stop hand-assembling acceptance flow shape.
It should call:

- `acceptance_runtime.runner.run_acceptance_graph(...)`

### Calibration

`acceptance_core.calibration` should compare:

- final review output
- field drift
- step artifact drift
- graph transition drift

## 9. Recommended Implementation Order

### Task 1: Add graph model and registry

Create:

- `src/spec_orch/acceptance_runtime/graph_models.py`
- `src/spec_orch/acceptance_runtime/graph_registry.py`
- `tests/unit/test_acceptance_runtime_registry.py`

### Task 2: Add per-step artifact persistence

Create:

- `src/spec_orch/acceptance_runtime/artifacts.py`
- `tests/unit/test_acceptance_runtime_artifacts.py`

### Task 3: Add step executor with step-scoped prompts

Create:

- `src/spec_orch/acceptance_runtime/prompts.py`
- `src/spec_orch/acceptance_runtime/step_executor.py`
- `tests/unit/test_acceptance_runtime_step_executor.py`

### Task 4: Add bounded graph runner

Create:

- `src/spec_orch/acceptance_runtime/runner.py`
- `tests/unit/test_acceptance_runtime_runner.py`

### Task 5: Integrate routing -> graph profile -> runner

Modify:

- `src/spec_orch/services/round_orchestrator.py`
- `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `tests/unit/test_round_orchestrator.py`

### Task 6: Expose graph artifacts to dashboard and calibration

Modify:

- `src/spec_orch/dashboard/surfaces.py`
- `src/spec_orch/acceptance_core/calibration.py`
- `tests/unit/test_dashboard_api.py`
- `tests/unit/test_acceptance_core_calibration.py`

## 10. What Is Not Hardcoded

Do **not** hardcode:

- evaluator wording
- critique phrasing
- candidate wording
- review summary prose
- surface-specific heuristics that belong to packs/prompts

## 11. What Is Hardcoded On Purpose

Do hardcode, in code-owned registries:

- graph names
- step order
- transition rules
- budget ceilings
- artifact schemas
- required step outputs

This is what makes workflow tuning measurable and safe.
