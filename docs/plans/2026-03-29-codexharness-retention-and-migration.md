# Codexharness Retention and Migration Register

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve the high-value `codexharness` work that overlaps with the new architecture program without letting `codexharness` continue as a competing planning source of truth.

**Architecture:** `llm_planner_orch` is the canonical planning worktree. `codexharness` contains active acceptance/judgment exploration, role-constitution work, and calibration assets that should be retained as draft material and later migrated through `runtime_core`, `decision_core`, and `Acceptance Judgment and Calibration` rather than being merged wholesale.

**Tech Stack:** Git worktrees, Python 3.13, markdown planning docs, unified diffs as migration assets, current `src/spec_orch` package tree.

---

## 1. Retention Categories

This register uses three categories:

- `must-retain`
- `retain-as-reference`
- `ignore-as-runtime-noise`

## 2. Must-Retain Assets

These should be preserved in `llm_planner_orch` as migration inputs or draft assets.

### 2.1 Draft planning docs

- `codexharness/docs/plans/2026-03-29-acceptance-judgment-model.md`

Why:

- it defines the acceptance judgment ontology now being promoted into the architecture program
- it is directly relevant to `Epic 4: Acceptance Judgment and Calibration`

### 2.2 Role constitution / prompt discipline code

- `codexharness/src/spec_orch/services/constitutions.py`
- `codexharness/src/spec_orch/services/litellm_supervisor_adapter.py`
- `codexharness/src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `codexharness/src/spec_orch/services/evolution/intent_evolver.py`
- `codexharness/src/spec_orch/services/evolution/prompt_evolver.py`

### 2.3 Supporting tests

- `codexharness/tests/unit/test_litellm_acceptance_evaluator.py`
- `codexharness/tests/unit/test_litellm_supervisor_adapter.py`
- `codexharness/tests/unit/test_muscle_evolvers.py`
- `codexharness/tests/unit/test_prompt_evolver.py`

Why:

- this is not runtime noise
- it is a concrete draft of `role constitution / role prompt discipline`
- conceptually it belongs close to `decision_core`
- even if we do not migrate it 1:1, we should preserve it as exact source material

## 3. Retain-As-Reference Assets

These have information value but are not the current canonical plan:

- `codexharness/docs/plans/2026-03-29-son-264-runtime-responsibility-split.md`
- `codexharness/progress.md`
- `codexharness/task_plan.md`

Why:

- useful for runtime responsibility thinking
- not the canonical program plan
- should not outrank the main planning docs in `llm_planner_orch`

## 4. Ignore-As-Runtime-Noise Assets

These should not drive the next architecture phase:

- dogfood/replay artifacts under `docs/specs/operator-console-dogfood-smoke/...`
- `acceptance_review.json`
- `browser_evidence.json`
- `round_summary.json`
- `round_decision.json`
- `artifacts.json`
- `campaign.json`
- `visual/*.png`
- `supervisor_review.md`
- `task.spec.md`
- telemetry logs under `.../telemetry/`

Why:

- these are runtime evidence carriers
- they are useful for local investigation, not as planning truth

## 5. Practical Handling Rule

The current recommendation is:

1. Preserve must-retain assets in `llm_planner_orch`
2. Do not continue expanding them in `codexharness`
3. Keep `llm_planner_orch` as the main planning worktree
4. Later migrate or re-implement through the extracted seams instead of cherry-picking blindly

## 6. Preservation Artifacts

The following preservation artifacts should exist in `llm_planner_orch`:

- copied draft doc for acceptance judgment model
- patch bundle covering the must-retain code/test diffs
- this migration register

These assets are inputs to later work under:

- `Decision Core Extraction`
- `Acceptance Judgment and Calibration`
- possibly `Evolution and Policy Promotion Linkage`

## 7. Bottom Line

`codexharness` should stop being the place where the program shape evolves.

But the branch contains important draft material that should be treated as:

- preserved
- indexed
- deliberately migrated later

Not:

- discarded
- merged wholesale
- or allowed to silently diverge from the canonical program plan.
