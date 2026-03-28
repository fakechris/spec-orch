# Workflow Acceptance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** finish the first complete Workflow Acceptance epic slice so dashboard operator workflows can be executed end-to-end with stable selectors, step-level assertions, and repeatable repair-loop regression checks.

**Architecture:** Extend the acceptance system with a dedicated `workflow` mode, drive browser interactions through stable selector-based targets instead of ambiguous text clicks, and persist/assert step-level workflow expectations so failures are actionable. Then lock the behavior with workflow-focused calibration fixtures and dashboard regression tests.

**Tech Stack:** Python 3.13, dataclasses, Playwright-based browser evidence, pytest, FastAPI dashboard shell, Linear-aligned roadmap docs.

### Task 1: Add workflow acceptance mode and campaign contract

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Modify: `src/spec_orch/services/acceptance/prompt_composer.py`
- Test: `tests/unit/test_acceptance_models.py`
- Test: `tests/unit/test_acceptance_prompt_composer.py`

**Step 1: Write the failing tests**

- Add tests that require:
  - `AcceptanceMode.WORKFLOW`
  - workflow campaigns to round-trip through `AcceptanceCampaign.to_dict()/from_dict()`
  - workflow prompts to render workflow-specific guidance, rubric, and filing policy

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_models.py tests/unit/test_acceptance_prompt_composer.py -q
```

Expected: FAIL because workflow mode and workflow-specific prompt content do not exist yet.

**Step 3: Write minimal implementation**

- Add `AcceptanceMode.WORKFLOW`
- Keep `AcceptanceCampaign` backwards-compatible
- Teach `prompt_composer.py` a workflow-specific charter

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add src/spec_orch/domain/models.py src/spec_orch/services/acceptance/prompt_composer.py tests/unit/test_acceptance_models.py tests/unit/test_acceptance_prompt_composer.py
git commit -m "feat: add workflow acceptance mode"
```

### Task 2: Add selector-based workflow interaction steps and actionable step failures

**Files:**
- Modify: `src/spec_orch/services/visual/playwright_visual_eval.py`
- Modify: `src/spec_orch/services/acceptance/browser_evidence.py`
- Test: `tests/unit/test_playwright_visual_eval.py`
- Test: `tests/unit/test_browser_evidence.py`

**Step 1: Write the failing tests**

- Add tests for:
  - selector-based click steps using stable `data-automation-target` hooks
  - selector-based wait/assert steps
  - failed steps capturing actionable messages tied to the step description and selector

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_playwright_visual_eval.py tests/unit/test_browser_evidence.py -q
```

Expected: FAIL because only `click_text`/`wait_for_text` style interactions are supported.

**Step 3: Write minimal implementation**

- Add selector-driven workflow actions
- Preserve existing text-based actions for older acceptance fixtures
- Record step-level failures in `interaction_log` with explicit expected/action context

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add src/spec_orch/services/visual/playwright_visual_eval.py src/spec_orch/services/acceptance/browser_evidence.py tests/unit/test_playwright_visual_eval.py tests/unit/test_browser_evidence.py
git commit -m "feat: add selector-based workflow interactions"
```

### Task 3: Generate workflow campaigns and assertions from round orchestration

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Test: `tests/unit/test_round_orchestrator.py`

**Step 1: Write the failing tests**

- Add tests that require:
  - `workflow` mode campaigns to target real operator flows
  - mission/launcher/transcript/approval routes to get stable selector steps
  - workflow campaigns to emit actionable assertion expectations instead of route-only checks

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_round_orchestrator.py -q
```

Expected: FAIL because the orchestrator currently only builds feature/impact/exploratory campaigns with text-click plans.

**Step 3: Write minimal implementation**

- Add workflow-mode campaign construction
- Build route-specific selector steps from dashboard automation hooks
- Add explicit assertion/recommended-next-step semantics for workflow failures

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add src/spec_orch/services/round_orchestrator.py tests/unit/test_round_orchestrator.py
git commit -m "feat: add workflow acceptance campaigns"
```

### Task 4: Lock workflow dogfood in calibration fixtures and dashboard regression tests

**Files:**
- Create: `tests/fixtures/acceptance/workflow_dashboard_repair_loop.json`
- Modify: `tests/unit/test_acceptance_calibration_suite.py`
- Modify: `tests/unit/test_dashboard_package.py`
- Modify: `task_plan.md`
- Modify: `progress.md`

**Step 1: Write the failing tests**

- Add fixture-backed tests that require:
  - workflow acceptance reviews to round-trip cleanly
  - workflow filing behavior to stay conservative and repair-oriented
  - dashboard stable automation targets to remain present in the rendered shell

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_calibration_suite.py tests/unit/test_dashboard_package.py -q
```

Expected: FAIL until the workflow fixture and regression expectations are added.

**Step 3: Write minimal implementation**

- Add the fixture
- Update regression tests
- Record the finished slice in plan/progress docs

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add tests/fixtures/acceptance/workflow_dashboard_repair_loop.json tests/unit/test_acceptance_calibration_suite.py tests/unit/test_dashboard_package.py task_plan.md progress.md
git commit -m "test: add workflow acceptance regression fixture"
```

### Task 5: Full verification

**Files:**
- Verify only

**Step 1: Run focused workflow-acceptance verification**

```bash
uv run --python 3.13 python -m pytest \
  tests/unit/test_acceptance_models.py \
  tests/unit/test_acceptance_prompt_composer.py \
  tests/unit/test_playwright_visual_eval.py \
  tests/unit/test_browser_evidence.py \
  tests/unit/test_round_orchestrator.py \
  tests/unit/test_acceptance_calibration_suite.py \
  tests/unit/test_dashboard_package.py -q
```

Expected: PASS

**Step 2: Run broader dashboard + full suite verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
uv run --python 3.13 python -m pytest -q
uv run --python 3.13 python -m ruff check src/ tests/
uv run --python 3.13 python -m ruff format --check src/ tests/
uv run --python 3.13 python -m mypy src/
```

Expected: PASS

**Step 3: Commit final integration**

```bash
git add .
git commit -m "feat: finish workflow acceptance epic"
```
