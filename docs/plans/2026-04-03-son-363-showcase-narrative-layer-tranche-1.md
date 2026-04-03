# SON-363 Showcase / Narrative Layer Tranche 1

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stand up the first canonical global showcase surface so operators can read archived acceptance releases and workspace-level workbench storylines from one narrative layer.

**Architecture:** Do not create a fourth competing source of truth. This tranche must consume existing acceptance-history bundles plus the canonical execution, judgment, and learning workbenches. The showcase surface is a read model and presentation layer only.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff

### Task 1: Lock the showcase contract in tests

**Files:**
- Add: `tests/unit/test_showcase_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`
- Modify: `tests/unit/test_dashboard_package.py`

**Step 1: Write the failing tests**

Require:
- a global `showcase` read model with `summary`, `release_timeline`, `workspace_storylines`, `highlights`, and `review_route`
- `/api/showcase` to expose that read model
- the dashboard shell to expose a stable `showcase` operator mode button

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
```

Expected: `FAIL` because the showcase service, API route, and operator mode do not exist yet.

### Task 2: Implement the showcase read model and dashboard mode

**Files:**
- Add: `src/spec_orch/services/showcase_workbench.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/__init__.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Implement the minimal tranche**

Implement:
- a global showcase read model sourced from `docs/acceptance-history/index.json`
- release timeline rows that point at archived bundle artifacts
- workspace storylines composed from execution, judgment, and learning workbench summaries
- a top-level dashboard `showcase` mode with a context rail

Keep:
- mission-local tabs unchanged
- showcase strictly downstream of existing workbench seams

**Step 2: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_showcase_workbench.py tests/unit/test_learning_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/showcase_workbench.py src/spec_orch/dashboard/app.py src/spec_orch/dashboard/api.py src/spec_orch/dashboard/__init__.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/missions.py tests/unit/test_showcase_workbench.py tests/unit/test_learning_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py
```

Expected: `PASS`

### Task 3: Run tranche closeout acceptance and archive the release

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
- source-run compare notes against `surface-cleanup-and-cutover-tranche-son-402-2026-04-03`

Refresh `docs/acceptance-history/index.json`.
