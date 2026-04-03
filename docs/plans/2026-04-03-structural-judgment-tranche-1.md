# Structural Judgment Tranche 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic structural judgment channel beside semantic acceptance output so operators can distinguish workflow regressions, coverage gaps, and compare/baseline drift without depending on LLM interpretation.

**Architecture:** Keep semantic acceptance as the primary judgment source. The new structural channel is a read-side projection built only from existing acceptance review payloads, candidate queue state, compare overlay state, coverage metadata, and graph artifacts. It must surface cleanly in both mission-local and global Judgment Workbench views without creating a second review stack.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff, canonical acceptance harness, acceptance-history archive

### Task 1: Lock the structural channel contract in tests

**Files:**
- Add: `tests/unit/test_structural_judgment.py`
- Modify: `tests/unit/test_judgment_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Require:
- a mission-level structural judgment payload with `quality_signal`, `bottleneck`, `rule_violations`, `baseline_diff`, and `current_state`
- latest review payloads in the judgment substrate to carry that structural channel beside semantic judgment artifacts
- global Judgment Workbench summaries to surface structural regression and bottleneck counts plus a structural watch list
- mission and global dashboard API payloads to serialize the structural channel cleanly

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because structural judgment does not exist yet as a first-class channel.

### Task 2: Implement the deterministic structural judgment channel

**Files:**
- Add: `src/spec_orch/services/structural_judgment.py`
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/judgment_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Write the minimal implementation**

Implement:
- a deterministic structural read model derived from:
  - review status and confidence
  - coverage status and untested routes
  - candidate queue and repro state
  - compare overlay and baseline refs
  - graph artifact shape and route counts
- mission-local `structural_judgment` projection attached to the latest review and the mission workbench payload
- global workbench summary fields and `structural_watch` inventory for regressions and bottlenecks
- dashboard rendering for the structural channel in both mission-local and global Judgment Workbench surfaces

Keep:
- no new evaluator calls
- no write actions
- no duplication of semantic findings inside the structural channel

**Step 2: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/structural_judgment.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/judgment_workbench.py src/spec_orch/dashboard/app.py tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
```

Expected: `PASS`

### Task 3: Close the tranche with formal acceptance and archive it

**Files:**
- Modify: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify: `docs/acceptance-history/index.json`
- Create: `docs/acceptance-history/releases/<release-id>/manifest.json`
- Create: `docs/acceptance-history/releases/<release-id>/status.json`
- Create: `docs/acceptance-history/releases/<release-id>/source_runs.json`
- Create: `docs/acceptance-history/releases/<release-id>/artifacts.json`
- Create: `docs/acceptance-history/releases/<release-id>/findings.json`
- Create: `docs/acceptance-history/releases/<release-id>/summary.md`

**Step 1: Run canonical acceptance**

Run:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

If a `harness_bug` appears, fix it before rerunning.

**Step 2: Write the release bundle**

Archive:
- consolidated status
- source runs
- findings and issue proposals
- source-run compare notes versus `concurrency-and-admission-control-tranche-son-412-2026-04-03`

Refresh `docs/acceptance-history/index.json`.
