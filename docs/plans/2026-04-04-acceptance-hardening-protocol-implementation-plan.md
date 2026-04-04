# Acceptance Hardening Protocol Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden acceptance and internal workflow discipline by adding tranche review language, exploratory planning rounds, browser step markers, and stronger internal verification guidance.

**Architecture:** Extend the existing acceptance/hardening stack rather than redesigning it. Add new protocol carriers to the exploratory acceptance and browser evidence seams, then wire the resulting outputs into existing reports, docs, and closeout routines.

**Tech Stack:** Python 3.13, pytest, mypy, ruff, shell harness scripts, markdown docs.

### Task 1: Planning Files and Protocol Baseline

**Files:**
- Create: `task_plan.md`
- Create: `findings.md`
- Create: `progress.md`
- Create: `docs/plans/2026-04-04-acceptance-hardening-protocol-implementation-plan.md`

**Step 1: Capture current scope and constraints**

Write the planning files with the current goal, tranche order, and research-derived requirements.

**Step 2: Verify baseline**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 \
uv run --python 3.13 pytest tests/unit/test_stability_acceptance.py tests/unit/test_dashboard_api.py -q
```

Expected: pass on the unmodified baseline in the new worktree.

### Task 2: 5-Subsystem Review Checklist and Context Taxonomy

**Files:**
- Modify: `docs/agent-guides/run-pipeline.md`
- Modify: `docs/agent-guides/services.md`
- Modify: `docs/agent-guides/troubleshooting.md`
- Test/Verify: docs review only

**Step 1: Add fixed tranche review language**

Document the five review subsystems:
- `Instructions`
- `State`
- `Verification`
- `Scope`
- `Lifecycle`

Include a bottleneck-first rule: the lowest-scoring subsystem becomes the next hardening target.

**Step 2: Add context/memory taxonomy**

Document the five storage layers:
- `Active Context`
- `Working State`
- `Review Evidence`
- `Archive`
- `Promoted Learning`

**Step 3: Verify doc consistency**

Run:

```bash
rg -n "Instructions|Working State|Promoted Learning|bottleneck" docs/agent-guides
```

Expected: the new checklist/taxonomy language is present in the updated docs.

### Task 3: Exploratory Acceptance Planning Contract

**Files:**
- Modify: `src/spec_orch/services/fresh_acpx_e2e.py`
- Modify: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Modify: `tests/unit/test_fresh_acpx_e2e.py`
- Modify: `tests/unit/test_litellm_acceptance_evaluator.py`

**Step 1: Write failing tests**

Add tests that require exploratory review payloads to expose:
- `functional_plan`
- `adversarial_plan`
- `coverage_gaps`
- `merged_plan`

**Step 2: Run failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 \
uv run --python 3.13 pytest tests/unit/test_fresh_acpx_e2e.py tests/unit/test_litellm_acceptance_evaluator.py -q
```

Expected: fail because the new planning-round fields do not exist yet.

**Step 3: Write minimal implementation**

Extend the exploratory acceptance assembly/evaluation path to emit the three planning rounds and a merged execution plan without redesigning the broader campaign model.

**Step 4: Run passing tests**

Re-run the same test command and confirm pass.

### Task 4: Browser Acceptance Step Markers and Failure Artifact Contract

**Files:**
- Modify: `src/spec_orch/services/acceptance/browser_evidence.py`
- Modify: `src/spec_orch/services/stability_acceptance.py`
- Modify: `tests/unit/test_browser_evidence.py`
- Modify: `tests/unit/test_stability_acceptance.py`

**Step 1: Write failing tests**

Add tests that require browser evidence interactions to emit:
- `STEP_PASS`
- `STEP_FAIL`
- `STEP_SKIP`

And failure evidence payloads to include:
- `step_id`
- `expected`
- `actual`
- `screenshot_path`
- `before_snapshot_ref`
- `after_snapshot_ref`

**Step 2: Run failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 \
uv run --python 3.13 pytest tests/unit/test_browser_evidence.py tests/unit/test_stability_acceptance.py -q
```

Expected: fail because the current browser evidence contract lacks the new marker fields.

**Step 3: Write minimal implementation**

Add step marker and failure evidence carriers to browser evidence, then ensure stability acceptance/reporting preserves them.

**Step 4: Run passing tests**

Re-run the same tests and confirm pass.

### Task 5: Internal Workflow and Skill-Style Hardening

**Files:**
- Modify: `docs/agent-guides/run-pipeline.md`
- Modify: `docs/agent-guides/services.md`
- Modify: `docs/agent-guides/troubleshooting.md`

**Step 1: Add anti-rationalization and verification sections**

Apply the internal workflow template:
- `Overview`
- `When to Use`
- `Workflow`
- `Rules`
- `Common Rationalizations`
- `Red Flags`
- `Verification`

Only add this structure where it materially improves operator workflow clarity.

**Step 2: Verify docs**

Run:

```bash
rg -n "Common Rationalizations|Red Flags|Verification" docs/agent-guides
```

Expected: the updated docs contain the new sections.

### Task 6: Full Verification and Acceptance Closeout

**Files:**
- Modify: `docs/acceptance-history/index.json`
- Create: `docs/acceptance-history/releases/<new-bundle>/...`

**Step 1: Run focused Python verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest \
  tests/unit/test_fresh_acpx_e2e.py \
  tests/unit/test_litellm_acceptance_evaluator.py \
  tests/unit/test_browser_evidence.py \
  tests/unit/test_stability_acceptance.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/ tests/
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff format --check src/ tests/
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/
```

Expected: all green.

**Step 2: Run formal acceptance**

Run the canonical acceptance closeout sequence serially:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

**Step 3: Archive**

Write a new release bundle under `docs/acceptance-history/releases/` and update `docs/acceptance-history/index.json`.

**Step 4: Commit**

```bash
git add docs/agent-guides docs/plans src/spec_orch tests docs/acceptance-history
git commit -m "feat: harden acceptance protocol"
```
