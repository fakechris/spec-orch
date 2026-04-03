# SON-412 Concurrency and Admission Control Tranche 1

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn admission control from a read-side summary into a real runtime governor that records `admit / defer` decisions, feeds the execution substrate, and surfaces mission-local admission posture in the Execution Workbench.

**Architecture:** Do not invent a parallel queue system. This tranche must hang off the existing daemon budget seam, persist governor decisions under `.spec_orch/admission/`, and let the execution substrate and workbench consume those canonical carriers.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff, mypy, canonical acceptance harness

### Task 1: Lock the governor contract in tests

**Files:**
- Add: `tests/unit/test_admission_governor.py`
- Modify: `tests/unit/test_daemon.py`
- Modify: `tests/unit/test_execution_substrate.py`
- Modify: `tests/unit/test_execution_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Require:
- a daemon-side admission governor that records defer decisions when `max_concurrent` budget is saturated
- execution substrate carriers for `queue`, `resource_budgets`, `pressure_signals`, and `admission_decisions`
- mission-local execution workbench surfaces that expose admission posture counts and carrier details

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the admission governor module and the new substrate/workbench carriers do not exist yet.

### Task 2: Implement daemon-backed admission enforcement

**Files:**
- Add: `src/spec_orch/services/admission_governor.py`
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/services/execution_substrate.py`
- Modify: `src/spec_orch/services/execution_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Implement the minimal tranche**

Implement:
- a persisted admission decision log under `.spec_orch/admission/decisions.jsonl`
- daemon evaluation that records `admit` or `defer` before issue claim when `max_concurrent` budget is saturated
- execution substrate merge logic that lifts governor records into canonical queue, pressure, budget, and admission carriers
- mission-local execution workbench sections for admission posture, pressure signals, and resource budgets

Keep:
- queue enforcement bounded to the current daemon concurrency seam
- hotfix handling compatible with existing priority semantics
- dashboard changes read-only; no new write path from the UI in this tranche

**Step 2: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/admission_governor.py src/spec_orch/services/daemon.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/app.py tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/admission_governor.py src/spec_orch/services/daemon.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/execution_workbench.py
```

Expected: `PASS`

### Task 3: Close the tranche with formal acceptance and archive it

**Files:**
- Modify: `tests/unit/test_stability_acceptance.py`
- Modify: `tests/e2e/fresh_acpx_mission_smoke.sh`
- Modify: `tests/e2e/exploratory_acceptance_smoke.sh`
- Modify: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify: `docs/acceptance-history/index.json`
- Create: `docs/acceptance-history/releases/<release-id>/manifest.json`
- Create: `docs/acceptance-history/releases/<release-id>/status.json`
- Create: `docs/acceptance-history/releases/<release-id>/source_runs.json`
- Create: `docs/acceptance-history/releases/<release-id>/artifacts.json`
- Create: `docs/acceptance-history/releases/<release-id>/findings.json`
- Create: `docs/acceptance-history/releases/<release-id>/summary.md`

**Step 1: Run canonical acceptance serially**

Run:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

If a `harness_bug` appears, fix it before rerunning.

**Step 2: Archive the release**

Archive:
- consolidated status
- source runs
- findings and issue proposals
- source-run compare notes versus `showcase-narrative-layer-tranche-son-363-2026-04-03`

Refresh `docs/acceptance-history/index.json`.
