# SON-390 Judgment Workbench v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote the existing judgment substrate into a real Judgment Workbench surface with global and mission-level dashboard contracts.

**Architecture:** Reuse `build_mission_judgment_substrate()` as the canonical per-mission producer and add a thin `judgment_workbench` service that aggregates workspace-level judgment inventory across missions. Keep the old acceptance-review route working, but add dedicated judgment-workbench routes and dashboard surfaces that consume the new contract. The UI should stay read-only and operator-facing: overview, evidence, timeline, candidate findings, compare, and surface-pack state.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff

### Task 1: Write failing tests for the judgment workbench contract

**Files:**
- Modify: `tests/unit/test_judgment_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add tests that require:
- a global judgment workbench payload with:
  - `summary`
  - `workspaces`
  - `candidate_queue`
  - `compare_watch`
  - `review_route`
- a mission-level judgment workbench payload with:
  - `overview`
  - `evidence_panel`
  - `judgment_timeline`
  - `candidate_queue`
  - `compare_view`
  - `surface_pack_panel`
  - `review_route`
- mission detail embedding the new `judgment_workbench`

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the dedicated judgment workbench service and routes do not exist yet.

### Task 2: Implement the judgment workbench service and API seams

**Files:**
- Create: `src/spec_orch/services/judgment_workbench.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/__init__.py`

**Step 1: Write minimal implementation**

Implement:
- `build_judgment_workbench(repo_root)`
- `build_mission_judgment_workbench(repo_root, mission_id)`

Keep the contract read-only and derive from `build_mission_judgment_substrate()`:
- global `summary` across workspaces
- global `workspaces` list with overview counts and routes
- global candidate queue and compare watch inventory
- mission-level workbench returning the canonical judgment panels without dashboard-only reshaping

Expose:
- `/api/judgment-workbench`
- `/api/missions/{mission_id}/judgment-workbench`
- mission detail field `judgment_workbench`

**Step 2: Run tests to verify they pass**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `PASS`

### Task 3: Add Judgment Workbench dashboard surfaces

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`
- Test: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing test**

Extend dashboard API coverage so the new mode/tab contracts are required:
- top-level `mode=judgment` backed by `/api/judgment-workbench`
- mission `Judgment` tab backed by `/api/missions/{mission_id}/judgment-workbench`
- mission detail and context rail use `judgment_workbench` rather than raw acceptance-review-only wording

**Step 2: Run test to verify it fails**

Run the same focused pytest command and confirm the new assertions fail for the intended reason.

**Step 3: Write minimal implementation**

Add:
- `Judgment` operator mode beside `Execution`
- mission `Judgment` tab beside `Acceptance`
- rendering helpers for overview, evidence, timeline, candidate findings, compare, and surface pack

Keep `Acceptance` as the raw review/artifact entry point; make `Judgment` the operator-facing reasoning surface.

**Step 4: Run tests to verify they pass**

Run the same focused pytest command and confirm all tests pass.

### Task 4: Verify, run formal acceptance, and archive the tranche

**Files:**
- Modify: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify: `docs/acceptance-history/index.json`
- Create: `docs/acceptance-history/releases/<release-id>/manifest.json`
- Create: `docs/acceptance-history/releases/<release-id>/status.json`
- Create: `docs/acceptance-history/releases/<release-id>/source_runs.json`
- Create: `docs/acceptance-history/releases/<release-id>/artifacts.json`
- Create: `docs/acceptance-history/releases/<release-id>/findings.json`
- Create: `docs/acceptance-history/releases/<release-id>/summary.md`

**Step 1: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/judgment_workbench.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/__init__.py src/spec_orch/dashboard/app.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
```

**Step 2: Run tranche closeout acceptance**

Run:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

If a `harness_bug` appears, fix it before rerunning.

**Step 3: Write the release bundle**

Archive:
- consolidated status
- source runs
- classified findings
- release summary

Update `docs/acceptance-history/index.json`.
