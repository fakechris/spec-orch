# SON-363 Showcase / Narrative Layer Tranche 3

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend showcase from static lineage notes into explicit source-run compare narrative so operators can read what advanced, stayed, or regressed between adjacent release bundles.

**Architecture:** Keep showcase downstream-only. This tranche may derive compare carriers from adjacent `docs/acceptance-history` bundles and their `source_runs.json` payloads, but it must not introduce new mutation paths or a second acceptance history store.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff, mypy

### Task 1: Lock the compare narrative contract in tests

**Files:**
- Modify: `tests/unit/test_showcase_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`
- Modify: `tests/unit/test_dashboard_package.py`

**Step 1: Write the failing tests**

Require:
- release timeline rows to expose `compare_target_release_id`
- release timeline rows to expose structured `source_run_compare`
- workspace storylines to expose a `source_run_compare_summary` through `lineage_drilldown`
- the dashboard shell to render compare target and source-run compare copy

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q -k showcase
```

Expected: `FAIL` because showcase does not yet project explicit compare carriers.

### Task 2: Implement minimal compare narrative carriers

**Files:**
- Modify: `src/spec_orch/services/showcase_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Implement the tranche**

Implement:
- adjacent-release compare derived from `source_runs.json`
- stable ordering for compare summaries using canonical acceptance suite order
- release-level compare carrier exposure in showcase service
- storyline-level compare summary exposure via latest linked release
- minimal showcase rendering for compare target and compare summary

Keep:
- showcase strictly read-only
- compare logic local to showcase service
- no new routes or mutation APIs

**Step 2: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q -k showcase
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/showcase_workbench.py src/spec_orch/dashboard/app.py tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/showcase_workbench.py
```

Expected: `PASS`

### Task 3: Decide closeout depth

If the tranche remains a showcase read-side extension only, focused verification is sufficient before commit.

If the tranche triggers a full dashboard release discipline pass, rerun canonical acceptance, archive a new bundle under `docs/acceptance-history/releases/`, and refresh `docs/acceptance-history/index.json`.
