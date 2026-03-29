# SON-265 Dashboard Critique Rubric Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dashboard-specific exploratory critique rubric that turns bounded exploratory evidence into high-quality operator-facing critique instead of verification-biased pass/warn output.

**Architecture:** Keep browser control and route expansion unchanged from `SON-264`. Strengthen the evaluator side: explicit dashboard critique axes in the prompt, structured critique metadata in the acceptance result, and deterministic synthesis for low-signal exploratory outputs. Lock behavior with dashboard-specific calibration fixtures and two runtime dogfood loops.

**Tech Stack:** Python, pytest, mypy, ruff, existing LiteLLM acceptance evaluator, dashboard dogfood artifacts.

### Task 1: Add dashboard-specific exploratory critique metadata to the domain model

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Test: `tests/unit/test_acceptance_models.py`

**Step 1: Write the failing test**

Add model tests that build exploratory findings / proposals with dashboard critique metadata:

- `critique_axis`
- `operator_task`
- `why_it_matters`
- `hold_reason`

and verify `to_dict()` / `from_dict()` preserve them.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_models.py -q -k dashboard_critique_metadata`
Expected: FAIL because the metadata fields do not exist yet.

**Step 3: Write minimal implementation**

Update the acceptance finding / proposal models to carry the new optional metadata without changing non-exploratory behavior.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_models.py -q -k dashboard_critique_metadata`
Expected: PASS

### Task 2: Strengthen the exploratory prompt with dashboard critique axes

**Files:**
- Modify: `src/spec_orch/services/acceptance/prompt_composer.py`
- Test: `tests/unit/test_acceptance_prompt_composer.py`

**Step 1: Write the failing test**

Add a prompt composer test asserting exploratory prompts mention:

- surface orientation
- evidence discoverability
- terminology clarity
- task continuity
- operator confidence / trust signaling
- zero-finding explanation requirement

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_prompt_composer.py -q -k dashboard_exploratory_rubric`
Expected: FAIL because the prompt only contains generic exploratory guidance.

**Step 3: Write minimal implementation**

Render a dashboard-specific rubric section when:

- `campaign.mode == exploratory`
- the campaign targets dashboard/operator-console routes

Keep the guidance narrow and operator-facing.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_prompt_composer.py -q -k dashboard_exploratory_rubric`
Expected: PASS

### Task 3: Upgrade evaluator synthesis from transcript-only gap handling to axis-based critique handling

**Files:**
- Modify: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Test: `tests/unit/test_litellm_acceptance_evaluator.py`

**Step 1: Write the failing tests**

Add evaluator tests that prove:

- low-signal exploratory transcript output is rewritten into a structured evidence-discoverability critique
- zero-finding exploratory output with sufficient evidence becomes a held critique candidate instead of a silent pass
- summaries explain why no critique formed when evidence is insufficient

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_litellm_acceptance_evaluator.py -q -k exploratory_dashboard_critique`
Expected: FAIL because synthesis is still transcript-gap specific and metadata-free.

**Step 3: Write minimal implementation**

Refactor exploratory synthesis so it:

- maps evidence to a dashboard critique axis
- attaches `operator_task` and `why_it_matters`
- normalizes low-signal browser-error findings into operator-facing critique when warranted
- leaves clearly insufficient evidence as non-findings with explicit summary language

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_litellm_acceptance_evaluator.py -q -k exploratory_dashboard_critique`
Expected: PASS

### Task 4: Expand dashboard exploratory calibration fixtures

**Files:**
- Modify: `tests/fixtures/acceptance/exploratory_dashboard_ux_hold.json`
- Create: `tests/fixtures/acceptance/exploratory_dashboard_orientation_hold.json`
- Test: `tests/unit/test_acceptance_calibration_suite.py`

**Step 1: Write the failing tests**

Add calibration tests that assert:

- transcript discoverability fixture yields held critique on the right axis
- a second fixture yields a surface-orientation or task-continuity critique
- exploratory fixtures are not auto-filed by default

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_calibration_suite.py -q -k exploratory_dashboard`
Expected: FAIL because the second fixture does not exist and axis metadata is not asserted.

**Step 3: Write minimal implementation**

Update / add the fixtures with realistic browser evidence and acceptance payloads that reflect dashboard-specific critique.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_calibration_suite.py -q -k exploratory_dashboard`
Expected: PASS

### Task 5: Re-run internal dashboard exploratory dogfood

**Files:**
- Use existing operator dogfood spec outputs under `docs/specs/`
- Optionally update: `docs/plans/2026-03-29-son-264-exploratory-acceptance-implementation.md`

**Step 1: Run the internal exploratory replay**

Run the same operator-console exploratory loop used in `SON-264`.

**Step 2: Verify runtime output**

Confirm the new acceptance review:

- remains `coverage_status: complete`
- produces at least one dashboard critique with explicit axis metadata
- explains why the critique matters to an operator

**Step 3: Record the result**

Document the artifact path and summarize whether the critique quality improved.

### Task 6: Re-run fresh ACPX exploratory dogfood

**Files:**
- Use existing fresh mission exploratory outputs under `docs/specs/`
- Modify only if proof plumbing needs adjustment: `src/spec_orch/services/fresh_acpx_e2e.py`

**Step 1: Run the fresh ACPX exploratory loop**

Use the established fresh mission path and then run exploratory acceptance on the resulting mission.

**Step 2: Verify runtime output**

Confirm the new acceptance review:

- remains `coverage_status: complete`
- produces a dashboard-specific critique or explicitly explains why the evidence was insufficient
- does not regress to `feature_scoped`

**Step 3: Record the result**

Capture the artifact path and compare the critique language with the internal run.

### Task 7: Full verification pass

**Files:**
- Verify all touched files and updated tests

**Step 1: Run targeted tests**

Run:

- `uv run pytest tests/unit/test_acceptance_models.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_litellm_acceptance_evaluator.py tests/unit/test_acceptance_calibration_suite.py -q`

Expected: PASS

**Step 2: Run static checks**

Run:

- `uv run mypy src/spec_orch/domain/models.py src/spec_orch/services/acceptance/prompt_composer.py src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `uv run ruff check src/spec_orch/domain/models.py src/spec_orch/services/acceptance/prompt_composer.py src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py tests/unit/test_acceptance_models.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_litellm_acceptance_evaluator.py tests/unit/test_acceptance_calibration_suite.py`
- `uv run ruff format --check src/spec_orch/domain/models.py src/spec_orch/services/acceptance/prompt_composer.py src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py tests/unit/test_acceptance_models.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_litellm_acceptance_evaluator.py tests/unit/test_acceptance_calibration_suite.py`

Expected: PASS

**Step 3: Run broader regression**

Run: `uv run pytest -q`
Expected: PASS

### Task 8: Review readiness

**Step 1: Check success criteria**

Do not open a PR unless all are true:

- internal exploratory runtime produces a high-quality dashboard critique
- fresh ACPX exploratory runtime also produces a high-quality critique or explicit insufficiency explanation
- critique is not limited to generic browser-error rewriting
- at least two dashboard critique axes are represented between fixtures and runtime runs

**Step 2: Commit**

Only after the above is true:

```bash
git add docs/plans/2026-03-29-son-265-dashboard-critique-rubric-design.md \
  docs/plans/2026-03-29-son-265-dashboard-critique-rubric-implementation.md \
  src/spec_orch/domain/models.py \
  src/spec_orch/services/acceptance/prompt_composer.py \
  src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py \
  tests/unit/test_acceptance_models.py \
  tests/unit/test_acceptance_prompt_composer.py \
  tests/unit/test_litellm_acceptance_evaluator.py \
  tests/unit/test_acceptance_calibration_suite.py \
  tests/fixtures/acceptance/exploratory_dashboard_ux_hold.json \
  tests/fixtures/acceptance/exploratory_dashboard_orientation_hold.json
git commit -m "feat: add dashboard exploratory critique rubric"
```
