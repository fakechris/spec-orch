# SON-396 Learning Workbench v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a visible Learning Workbench over existing memory, fixture-graduation, evolution-promotion, and acceptance-history seams.

**Architecture:** Keep this tranche read-only. Reuse `MemoryService` analytics, fixture-candidate seed/history files, `PromotionRegistry`, and `docs/acceptance-history` as the canonical producers. Add a `learning_workbench` service that emits global and mission-level read models for overview, promotion timeline, repeated patterns, fixture registry, memory links, evolution/policy history, and archive lineage. Then expose dedicated dashboard routes plus a top-level learning mode and mission learning tab.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff

### Task 1: Write failing tests for Learning Workbench read models

**Files:**
- Create: `tests/unit/test_learning_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add tests that require:
- a global learning workbench payload with:
  - `summary`
  - `workspaces`
  - `promotion_timeline`
  - `patterns`
  - `fixture_registry`
  - `memory_links`
  - `evolution_registry`
  - `archive_lineage`
  - `review_route`
- a mission-level learning workbench payload with:
  - `overview`
  - `promotion_timeline`
  - `patterns`
  - `fixture_registry`
  - `memory_links`
  - `evolution_registry`
  - `archive_lineage`
  - `review_route`
- mission detail embedding `learning_workbench`

Use real producers in test setup:
- reviewed acceptance findings via `MemoryService.record_acceptance_judgments()`
- fixture candidate seed/history via `acceptance_core.calibration`
- evolution promotions via `PromotionRegistry`
- archive lineage via `docs/acceptance-history/index.json`

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_learning_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the learning workbench service and routes do not exist yet.

### Task 2: Implement the learning workbench service and API seams

**Files:**
- Create: `src/spec_orch/services/learning_workbench.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/__init__.py`

**Step 1: Write minimal implementation**

Implement:
- `build_learning_workbench(repo_root)`
- `build_mission_learning_workbench(repo_root, mission_id)`

Read from:
- `MemoryService` reviewed findings / active learning slices / recent evolution journal
- `PromotionRegistry`
- `fixture_graduations.jsonl` and `operator/fixture_candidates/*.json`
- `docs/acceptance-history/index.json`

Required operator surfaces:
- overview counts
- promotion timeline
- repeated-pattern registry
- fixture and regression registry
- memory-linked findings
- evolution / policy history
- archive lineage

Expose:
- `/api/learning-workbench`
- `/api/missions/{mission_id}/learning-workbench`
- mission detail field `learning_workbench`

**Step 2: Run tests to verify they pass**

Run the same focused pytest command and confirm it goes green.

### Task 3: Add dashboard Learning Workbench surfaces

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`
- Test: `tests/unit/test_dashboard_api.py`

**Step 1: Extend the contract**

Add:
- top-level `Learning Workbench` mode beside `Execution` and `Judgment`
- mission-level `Learning` tab beside `Judgment`
- rendering helpers for:
  - overview
  - promotion timeline
  - patterns
  - fixtures
  - memory links
  - evolution / policy history
  - archive lineage

Keep this tranche read-only; do not add promotion-write actions yet.

**Step 2: Run focused tests**

Run the same focused pytest command and confirm it stays green.

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
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_learning_workbench.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/learning_workbench.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/api.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/__init__.py src/spec_orch/dashboard/app.py tests/unit/test_learning_workbench.py tests/unit/test_dashboard_api.py
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

Refresh `docs/acceptance-history/index.json`.
