# SON-384 Execution Workbench Tranche 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the first global Execution Workbench surface so operators can open one dashboard mode and see active work, agents, and runtimes without drilling into a specific mission first.

**Architecture:** Reuse the completed `SON-374` execution substrate as the only source of truth. This tranche stays read-only: it introduces a dedicated workbench read model, a dashboard API endpoint, and a top-level dashboard mode that renders `Active Work`, `Agents`, and `Runtimes` as first-class operator pages. Mission-local execution stays intact and becomes the workspace-local panel required by the spec.

**Tech Stack:** Python 3.13, FastAPI dashboard routes, vanilla dashboard JS, pytest unit tests, execution substrate snapshot.

### Task 1: Add failing tests for the global execution workbench contract

**Files:**
- Modify: `tests/unit/test_execution_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add focused tests that prove:
- `build_execution_workbench()` returns a global summary row
- the global payload exposes `active_work`, `agents`, and `runtimes` as first-class surfaces
- `/api/execution-workbench` returns that payload unchanged
- the dashboard shell can switch into a top-level `execution` mode without relying on mission detail only

**Step 2: Run the failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the global workbench service and endpoint do not exist yet.

### Task 2: Implement the global workbench read model and API

**Files:**
- Modify: `src/spec_orch/services/execution_workbench.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/__init__.py`
- Modify: `src/spec_orch/dashboard/routes.py`

**Step 1: Add the global read model**

Implement `build_execution_workbench(repo_root)` on top of `build_execution_substrate_snapshot()` and keep the payload operator-facing:
- summary row with running, queued, stalled, degraded-runtime, and intervention-needed counts
- `active_work`, `agents`, and `runtimes` sections
- queue / intervention / pressure / recent event support needed by the UI

**Step 2: Expose the API seam**

Add `_gather_execution_workbench(repo_root)` and `/api/execution-workbench`.
Do not duplicate substrate logic inside dashboard code.

**Step 3: Re-run the focused tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `PASS`.

### Task 3: Add the dashboard top-level execution mode

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Add the new mode and loader**

Load `/api/execution-workbench` during dashboard refresh and store it in dedicated client state.

**Step 2: Render the global execution surfaces**

Add a top-level `execution` operator mode that renders:
- summary row
- `Active Work`
- `Agents`
- `Runtimes`

Keep the mission-local `Execution` tab unchanged.

**Step 3: Verify lint and broader compatibility**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/api.py src/spec_orch/dashboard/__init__.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/app.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

### Task 4: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

This tranche changes an operator-facing dashboard surface, so rerun the canonical acceptance suite at close.

**Step 2: Classify failures and fix harness bugs first**

If exploratory or dashboard acceptance fails, classify `harness_bug / n2n_bug / ux_gap`, fix `harness_bug` first, and rerun before archiving.

**Step 3: Archive the tranche**

If acceptance stays green, write a new `SON-384` release bundle and refresh `docs/acceptance-history/index.json` with source-run compare notes against the prior `SON-379/384` bundle.
