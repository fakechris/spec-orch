# SON-402 Surface Cleanup and Workbench Cutover Tranche 1

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Execution, Judgment, and Learning the canonical operator surfaces while retaining a thin compatibility bridge for raw acceptance artifacts.

**Architecture:** Do not remove raw acceptance artifacts or legacy routes outright. Instead, normalize legacy `tab=acceptance` deep links onto the canonical `Judgment` workbench, remove `Acceptance` as a first-class mission tab, keep `/api/missions/{mission_id}/acceptance-review` alive for compatibility, and expose an explicit bridge from `Judgment` back to the raw acceptance artifact route. This tranche closes the first visible cutover loop without changing acceptance producers.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff

### Task 1: Lock the cutover behavior in tests

**Files:**
- Modify: `tests/unit/test_dashboard_api.py`
- Modify: `tests/unit/test_dashboard_package.py`
- Modify: `tests/unit/test_judgment_substrate.py`

**Step 1: Write the failing tests**

Require:
- legacy `tab=acceptance` route normalization to canonical `tab=judgment`
- mission acceptance-review payloads to advertise canonical `review_route`
- dashboard source to remove the `Acceptance` mission tab
- Judgment Workbench to expose a raw acceptance bridge
- judgment substrate known routes to treat `judgment` as the canonical mission review surface

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
```

Expected: `FAIL` because the dashboard and judgment read models still point to legacy acceptance surfaces.

### Task 2: Implement the first cutover seam

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/judgment_workbench.py`

**Step 1: Write minimal implementation**

Implement:
- route normalization from `acceptance -> judgment`
- canonical `review_route` values for mission acceptance/judgment payloads
- removal of the `Acceptance` mission tab from the canonical tab list
- a visible `Open raw acceptance artifact` bridge inside Judgment Workbench

Keep:
- `/api/missions/{mission_id}/acceptance-review`
- raw acceptance artifacts and round-level acceptance routes as compatibility seams

**Step 2: Run tests to verify they pass**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
```

Expected: `PASS`

### Task 3: Document the canonical operator surfaces

**Files:**
- Modify: `docs/agent-guides/run-pipeline.md`
- Modify: `docs/agent-guides/services.md`

Document:
- `Execution`, `Judgment`, and `Learning` are now the canonical operator workbench surfaces
- `Acceptance` is retained only as a raw artifact / compatibility bridge
- operators should use Judgment for the primary review workflow after cutover

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
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_missions.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/dashboard/app.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/judgment_workbench.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py
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
