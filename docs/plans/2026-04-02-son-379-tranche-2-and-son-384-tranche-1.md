# SON-379 Tranche 2 and SON-384 Tranche 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the second judgment-substrate tranche by exposing a complete judgment workbench read model, then land the first Execution Workbench tranche as a mission-level operator surface that consumes the runtime substrate rather than bespoke dashboard logic.

**Architecture:** Reuse the existing shared operator semantics, `build_mission_judgment_substrate`, and `build_execution_substrate_snapshot` as the canonical sources. Extend the judgment substrate with workbench-facing inventory/grouping objects for evidence, candidate review, and compare drift. Then add a mission-scoped execution workbench service plus API/mission-detail integration so the dashboard shell can render a real execution tab over canonical substrate carriers.

**Tech Stack:** Python 3.13, FastAPI dashboard routes, dataclasses/shared operator semantics, mission dashboard JS in `app.py`, pytest unit tests, formal acceptance harness.

### Task 1: Write failing tests for judgment workbench and execution workbench read models

**Files:**
- Modify: `tests/unit/test_judgment_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`
- Modify if needed: `tests/unit/test_operator_semantics.py`

**Step 1: Add failing judgment-side tests**

Add tests that prove `build_mission_judgment_substrate(...)` now returns a workbench-facing judgment shape with:
- `overview`
- `evidence_panel`
- `candidate_queue`
- `compare_view`
- grouped judgment objects that preserve the existing `latest_review` payload

**Step 2: Add failing execution-side tests**

Add tests that prove:
- a new mission-level execution workbench payload can be gathered from runtime chain + execution substrate
- `/api/missions/{mission_id}/execution-workbench` exists
- `/api/missions/{mission_id}/detail` includes `execution_workbench`

**Step 3: Run tests to verify RED**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the richer judgment read model and mission execution workbench contract do not exist yet.

### Task 2: Implement SON-379 tranche 2 judgment workbench read model

**Files:**
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/operator_semantics.py`
- Modify if needed: `src/spec_orch/domain/operator_semantics.py`

**Step 1: Extend the substrate output**

Add workbench-facing read models synthesized from the current canonical carriers:
- `overview` with current judgment summary
- `evidence_panel` from `EvidenceBundle`
- `candidate_queue` from candidate findings
- `compare_view` from `CompareOverlay`
- `surface_pack_panel` from `SurfacePack`

Keep the existing acceptance-review API shape backward compatible. These are additive fields, not replacements.

**Step 2: Keep the substrate canonical**

Do not embed dashboard-only formatting. The new objects should still read like judgment substrate outputs that a future Judgment Workbench can consume unchanged.

### Task 3: Implement SON-384 tranche 1 execution workbench surface

**Files:**
- Create: `src/spec_orch/services/execution_workbench.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Add a mission-scoped execution workbench service**

Build a service that derives a workspace-local execution workbench payload using:
- `runtime_chain`
- mission-local slices of `build_execution_substrate_snapshot(...)`
- current mission actions

Minimum output:
- `overview`
- `active_work`
- `event_trail`
- `queue`
- `interventions`
- `runtime`
- `agents`
- `available_actions`
- `review_route`

**Step 2: Expose the payload in dashboard APIs**

Add:
- `/api/missions/{mission_id}/execution-workbench`
- `detail["execution_workbench"]`

Keep current mission detail fields stable.

**Step 3: Render a first execution workbench tab**

Add an `Execution` mission tab in `src/spec_orch/dashboard/app.py` that renders the canonical execution payload with:
- current active work card
- recent event trail
- queue/intervention state
- runtime summary
- available actions

This tranche is read-only. No new action handlers beyond existing mission actions.

### Task 4: Verify focused regression

**Files:**
- Modify if needed: the files above only

**Step 1: Run focused tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py tests/unit/test_execution_substrate.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/judgment_substrate.py src/spec_orch/services/operator_semantics.py src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/api.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/app.py tests/unit/test_operator_semantics.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py tests/unit/test_execution_substrate.py
```

Expected: all pass.

### Task 5: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

Run the full acceptance gate after both changes land.

**Step 2: Classify findings**

If any findings appear:
- classify `harness_bug` / `n2n_bug` / `ux_gap`
- fix `harness_bug` first
- rerun acceptance

**Step 3: Archive the tranche**

If acceptance is green, write a new release bundle covering `SON-379 tranche 2` and `SON-384 tranche 1`, then refresh `docs/acceptance-history/index.json` with source-run compare notes versus the `SON-379 tranche 1` bundle.
