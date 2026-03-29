# SON-264 Exploratory Acceptance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a bounded exploratory acceptance planner that compiles range-specific exploratory campaigns, carries an explicit exploratory contract through the evaluator prompt, and locks the behavior with calibration fixtures.

**Architecture:** Extend `AcceptanceCampaign` with exploratory-only contract fields instead of inventing a second campaign type. Keep route expansion deterministic in `RoundOrchestrator`, then let the evaluator consume a structured exploratory contract in `prompt_composer` so LLM reasoning stays bounded by harness-owned budgets and stop conditions.

**Tech Stack:** Python 3.11, pytest, dataclasses, existing acceptance orchestrator and prompt composer pipeline.

---

### Task 1: Extend AcceptanceCampaign with exploratory contract fields

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Test: `tests/unit/test_acceptance_models.py`

**Step 1: Write the failing test**

Add a round-trip test that builds an exploratory `AcceptanceCampaign` with:
- `seed_routes`
- `allowed_expansions`
- `critique_focus`
- `stop_conditions`
- `evidence_budget`

Assert `to_dict()` and `from_dict()` preserve the values.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_models.py -q -k exploratory_contract`
Expected: FAIL because `AcceptanceCampaign` does not accept or serialize the new exploratory fields.

**Step 3: Write minimal implementation**

Update `AcceptanceCampaign` to:
- add the new exploratory fields with sensible defaults
- serialize them in `to_dict()`
- restore them in `from_dict()`

Keep the fields generic so they remain reusable by future exploratory suites.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_models.py -q -k exploratory_contract`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/domain/models.py tests/unit/test_acceptance_models.py
git commit -m "feat: add exploratory acceptance contract fields"
```

### Task 2: Compile bounded exploratory campaigns in RoundOrchestrator

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Test: `tests/unit/test_round_orchestrator.py`

**Step 1: Write the failing test**

Add tests that assert exploratory campaign compilation:
- starts from deterministic `seed_routes`
- expands into bounded related routes from review routes
- records `allowed_expansions`, `critique_focus`, `stop_conditions`, and `evidence_budget`
- builds route-specific interaction plans for exploratory mission routes without reusing the workflow tab sweep wholesale

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_round_orchestrator.py -q -k exploratory_campaign`
Expected: FAIL because exploratory campaigns currently only set wide budgets plus generic tab-sweep interactions.

**Step 3: Write minimal implementation**

Implement helper methods in `RoundOrchestrator` to:
- derive exploratory seed routes
- deterministically expand related routes within budget
- set exploratory contract metadata
- build minimal exploratory interaction plans tied to the selected exploratory surfaces

Do not let the LLM choose routes here; this remains harness-owned logic.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_round_orchestrator.py -q -k exploratory_campaign`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/round_orchestrator.py tests/unit/test_round_orchestrator.py
git commit -m "feat: add bounded exploratory acceptance planner"
```

### Task 3: Add an explicit exploratory contract section to acceptance prompts

**Files:**
- Modify: `src/spec_orch/services/acceptance/prompt_composer.py`
- Test: `tests/unit/test_acceptance_prompt_composer.py`

**Step 1: Write the failing test**

Add a prompt composer test that expects exploratory prompts to include:
- `## Exploratory Contract`
- seed routes
- allowed expansions
- critique focus
- stop conditions
- evidence budget

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_prompt_composer.py -q -k exploratory_contract`
Expected: FAIL because the prompt only includes broad exploratory guidance today.

**Step 3: Write minimal implementation**

Update `compose_acceptance_prompt()` to render a dedicated exploratory contract section when `campaign.mode` is `EXPLORATORY`.

Keep workflow and exploratory contracts distinct.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_prompt_composer.py -q -k exploratory_contract`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/acceptance/prompt_composer.py tests/unit/test_acceptance_prompt_composer.py
git commit -m "feat: add exploratory acceptance prompt contract"
```

### Task 4: Refresh exploratory calibration fixture

**Files:**
- Modify: `tests/fixtures/acceptance/exploratory_dashboard_ux_hold.json`
- Test: `tests/unit/test_acceptance_calibration_suite.py`

**Step 1: Write the failing test**

Add assertions that the exploratory calibration fixture carries the new exploratory contract fields and still results in held, non-filed UX critique.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_acceptance_calibration_suite.py -q -k exploratory`
Expected: FAIL because the fixture does not yet include the new exploratory contract payload.

**Step 3: Write minimal implementation**

Update the fixture to include the new exploratory contract fields while preserving the current filing expectations.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_acceptance_calibration_suite.py -q -k exploratory`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/fixtures/acceptance/exploratory_dashboard_ux_hold.json tests/unit/test_acceptance_calibration_suite.py
git commit -m "test: refresh exploratory acceptance calibration fixture"
```

### Task 5: Full verification sweep

**Files:**
- Verify: `src/spec_orch/domain/models.py`
- Verify: `src/spec_orch/services/round_orchestrator.py`
- Verify: `src/spec_orch/services/acceptance/prompt_composer.py`
- Verify: `tests/unit/test_acceptance_models.py`
- Verify: `tests/unit/test_round_orchestrator.py`
- Verify: `tests/unit/test_acceptance_prompt_composer.py`
- Verify: `tests/unit/test_acceptance_calibration_suite.py`

**Step 1: Run focused acceptance verification**

Run:
```bash
uv run pytest tests/unit/test_acceptance_models.py tests/unit/test_round_orchestrator.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_acceptance_calibration_suite.py -q
```
Expected: PASS

**Step 2: Run static checks on touched code**

Run:
```bash
uv run ruff check src/spec_orch/domain/models.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/acceptance/prompt_composer.py tests/unit/test_acceptance_models.py tests/unit/test_round_orchestrator.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_acceptance_calibration_suite.py
uv run ruff format --check src/spec_orch/domain/models.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/acceptance/prompt_composer.py tests/unit/test_acceptance_models.py tests/unit/test_round_orchestrator.py tests/unit/test_acceptance_prompt_composer.py tests/unit/test_acceptance_calibration_suite.py
uv run mypy src/spec_orch/domain/models.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/acceptance/prompt_composer.py
```
Expected: PASS

**Step 3: Run full test suite**

Run:
```bash
uv run pytest -q
```
Expected: PASS

**Step 4: Commit**

```bash
git add docs/plans/2026-03-29-son-264-exploratory-acceptance-implementation.md
git commit -m "docs: capture son-264 exploratory acceptance plan"
```
