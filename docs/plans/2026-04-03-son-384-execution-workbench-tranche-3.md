# SON-384 Execution Workbench Tranche 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote browser and terminal activity into first-class Execution Workbench panels so operators can see execution surfaces without reading raw logs or acceptance artifacts directly.

**Architecture:** Keep the tranche read-only and artifact-backed. Reuse existing mission artifacts instead of inventing new runtime writers: browser visibility comes from round `browser_evidence.json` and exploratory browser evidence, while terminal visibility comes from worker `builder_report.json`, `activity.log`, and telemetry events. Extend the existing execution workbench read model so both the global execution mode and mission-local execution tab can render operator-friendly browser/terminal summaries.

**Tech Stack:** Python 3.13, FastAPI dashboard routes, vanilla dashboard JS, JSON artifacts, pytest unit tests.

### Task 1: Add failing tests for browser and terminal execution carriers

**Files:**
- Modify: `tests/unit/test_execution_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add focused tests that prove:
- `build_mission_execution_workbench()` returns a `browser_panel`
- `build_mission_execution_workbench()` returns a `terminal_panel`
- `build_execution_workbench()` returns global browser/terminal surface summaries
- the mission and global dashboard APIs pass those carriers through unchanged

**Step 2: Run the failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because browser/terminal workbench carriers are not exposed yet.

### Task 2: Implement browser and terminal workbench read models

**Files:**
- Modify: `src/spec_orch/services/execution_workbench.py`

**Step 1: Add browser panel projection**

Build an operator-facing browser panel from the newest available mission browser evidence:
- current browser task summary
- tested route count
- recent browser interactions
- screenshots/snapshot refs
- console/page error counts with reason text

**Step 2: Add terminal panel projection**

Build an operator-facing terminal panel from worker telemetry:
- session / packet identity
- command or worker summary
- recent terminal outcomes
- failure reason if present
- link back to the execution session via existing worker session / chain refs

**Step 3: Re-run the focused tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `PASS`.

### Task 3: Render the panels in the dashboard execution surfaces

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`

**Step 1: Extend mission-local execution UI**

Add browser and terminal sections to the mission `Execution` tab.

**Step 2: Extend global execution UI**

Add compact browser/terminal surface cards to the top-level `execution` mode so operators can see which workspaces have active browser or terminal evidence.

**Step 3: Verify lint and broader compatibility**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/app.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

### Task 4: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

This tranche changes execution-facing dashboard surfaces, so rerun the canonical acceptance suite at close.

**Step 2: Classify failures and fix harness bugs first**

If acceptance fails, classify `harness_bug / n2n_bug / ux_gap`, fix `harness_bug` first, and rerun before archiving.

**Step 3: Archive the tranche**

If acceptance stays green, write a new `SON-384` release bundle and refresh `docs/acceptance-history/index.json` with source-run compare notes against the prior `SON-384` bundle.
