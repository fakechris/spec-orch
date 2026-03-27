# Operator Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current prototype dashboard with a workbench-style operator console centered on Mission Detail and Run Transcript, while preserving the existing FastAPI dashboard entrypoint.

**Architecture:** Keep FastAPI as the dashboard backend and incrementally migrate away from the single-file `dashboard.py` HTML string into a static-asset-backed console. First establish a modular shell and mission/transcript APIs, then build the new Mission Detail and Run Transcript surfaces on top of those APIs. Do not introduce a full React/Vite frontend in this slice.

**Tech Stack:** Python, FastAPI, vanilla TypeScript/JavaScript served as static assets, existing SpecOrch services (`MissionService`, `MissionLifecycleManager`, `MissionExecutionService`, `RunEventLogger`, mission round artifacts)

## Scope

This plan covers:
- dashboard shell refactor
- operator-console layout primitives
- mission detail API and UI
- transcript API and UI
- basic inbox scaffolding
- docs and verification

This plan does **not** cover:
- full costs and budgets productization
- full approvals queue redesign
- visual QA gallery polish
- mobile-first optimization
- React rewrite

## Design Constraints

- Must follow `.impeccable.md`
- Must preserve mission context across subviews
- Must not feel like a BI dashboard
- Must not feel like a chat product
- Must not rely on nested card grids
- Must make human intervention actions stable and obvious

## Existing Surfaces To Reuse

### Backend
- `src/spec_orch/dashboard.py`
- `src/spec_orch/services/mission_service.py`
- `src/spec_orch/services/lifecycle_manager.py`
- `src/spec_orch/services/mission_execution_service.py`
- `src/spec_orch/services/run_event_logger.py`
- `src/spec_orch/services/activity_logger.py`
- mission artifacts under `docs/specs/<mission_id>/rounds/`
- worker telemetry under `docs/specs/<mission_id>/workers/<packet_id>/telemetry/`

### CLI / docs
- `src/spec_orch/cli/dashboard_commands.py`
- `src/spec_orch/cli/mission_commands.py`
- `docs/agent-guides/services.md`
- `docs/agent-guides/run-pipeline.md`

## Target File Structure

Create a dashboard package instead of growing `dashboard.py` further:

```text
src/spec_orch/dashboard/
  __init__.py
  app.py
  api.py
  mission_view_model.py
  transcript_builder.py
  static/
    operator-console.css
    operator-console.js
  templates/
    index.html
```

Keep `src/spec_orch/dashboard.py` as a thin compatibility wrapper that imports from `spec_orch.dashboard.app`.

## Task 1: Refactor Dashboard Entry Into Modules

**Files:**
- Create: `src/spec_orch/dashboard/__init__.py`
- Create: `src/spec_orch/dashboard/app.py`
- Create: `src/spec_orch/dashboard/api.py`
- Create: `src/spec_orch/dashboard/static/operator-console.css`
- Create: `src/spec_orch/dashboard/static/operator-console.js`
- Create: `src/spec_orch/dashboard/templates/index.html`
- Modify: `src/spec_orch/dashboard.py`
- Test: `tests/unit/test_dashboard_app.py`

**Step 1: Write the failing test**

Add tests that assert:
- `create_app()` still exists at `spec_orch.dashboard.create_app` or compatibility import path
- `/` serves HTML
- static assets are mounted or served

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_app.py -q
```

**Step 3: Write minimal implementation**

- Extract the app factory into `src/spec_orch/dashboard/app.py`
- Move routes into `api.py`
- Replace inline HTML/CSS/JS string with template + static files
- Keep the old module path working by re-exporting `create_app`

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_app.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard src/spec_orch/dashboard.py tests/unit/test_dashboard_app.py
git commit -m "refactor: modularize dashboard app shell"
```

## Task 2: Add Mission Detail View Model API

**Files:**
- Create: `src/spec_orch/dashboard/mission_view_model.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Test: `tests/unit/test_dashboard_mission_api.py`

**Step 1: Write the failing test**

Add tests for:
- `/api/missions/{mission_id}/detail`
- includes mission metadata, lifecycle state, current round, waves/packets, round summaries, recent artifacts, and intervention affordances

Expected JSON shape:
- `mission`
- `lifecycle`
- `rounds`
- `current_round`
- `packets`
- `actions`
- `artifacts`

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_mission_api.py -q
```

**Step 3: Write minimal implementation**

In `mission_view_model.py`, build a mission-detail assembler that reads:
- mission metadata from `MissionService`
- pipeline info from `check_pipeline`
- lifecycle state from `MissionLifecycleManager`
- plan from `docs/specs/<mission_id>/plan.json`
- round summaries from `docs/specs/<mission_id>/rounds/*/round_summary.json`
- decisions from `round_decision.json`
- review memo path from `supervisor_review.md`
- visual QA result from `visual_evaluation.json`

Expose a single backend-friendly JSON model for the UI.

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_mission_api.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/mission_view_model.py src/spec_orch/dashboard/api.py tests/unit/test_dashboard_mission_api.py
git commit -m "feat: add mission detail dashboard api"
```

## Task 3: Add Transcript Builder API

**Files:**
- Create: `src/spec_orch/dashboard/transcript_builder.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Test: `tests/unit/test_dashboard_transcript_builder.py`

**Step 1: Write the failing test**

Add tests for:
- `/api/missions/{mission_id}/packets/{packet_id}/transcript`
- merging `activity.log`, `events.jsonl`, `incoming_events.jsonl`
- grouping command bursts
- surfacing milestone events like approvals, retries, failures, supervisor decisions

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_transcript_builder.py -q
```

**Step 3: Write minimal implementation**

In `transcript_builder.py`:
- parse normalized events from `events.jsonl`
- parse raw agent events from `incoming_events.jsonl`
- parse human-readable activity stream from `activity.log`
- normalize to transcript blocks:
  - `message`
  - `tool`
  - `activity`
  - `stdout`
  - `event`
  - `supervisor`
  - `visual_finding`

Include links to related artifact files where possible.

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_transcript_builder.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/transcript_builder.py src/spec_orch/dashboard/api.py tests/unit/test_dashboard_transcript_builder.py
git commit -m "feat: add operator transcript api"
```

## Task 4: Build Operator Console Shell

**Files:**
- Modify: `src/spec_orch/dashboard/templates/index.html`
- Modify: `src/spec_orch/dashboard/static/operator-console.css`
- Modify: `src/spec_orch/dashboard/static/operator-console.js`
- Test: `tests/unit/test_dashboard_app.py`

**Step 1: Write the failing test**

Add tests for basic shell presence:
- global nav labels render
- mission workbench containers render
- transcript panel container renders

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_app.py -q
```

**Step 3: Write minimal implementation**

Build the new shell:
- left rail for mode navigation and mission list
- main canvas for selected mission view
- right action/context rail
- sticky mission header
- local mission tabs: `Overview`, `Transcript`, `Approvals`, `Visual QA`, `Artifacts`

Do not use the previous card-grid mission dashboard as the primary layout anymore.

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_app.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/templates/index.html src/spec_orch/dashboard/static/operator-console.css src/spec_orch/dashboard/static/operator-console.js tests/unit/test_dashboard_app.py
git commit -m "feat: add operator console dashboard shell"
```

## Task 5: Implement Mission Detail UI

**Files:**
- Modify: `src/spec_orch/dashboard/static/operator-console.js`
- Modify: `src/spec_orch/dashboard/static/operator-console.css`
- Test: `tests/unit/test_dashboard_mission_api.py`

**Step 1: Write the failing test**

Add tests around returned mission detail data contract used by UI, including:
- primary status
- blocking reason
- packet list
- current round
- action availability

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_mission_api.py -q
```

**Step 3: Write minimal implementation**

Render Mission Detail with:
- persistent mission header
- left execution structure pane
- center situation pane
- right intervention rail

Required surfaces:
- mission status
- round and wave
- packet swimlanes
- current supervisor decision
- latest anomalies
- approval prompts
- action buttons for resume / rerun / stop / inject guidance

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_mission_api.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/static/operator-console.js src/spec_orch/dashboard/static/operator-console.css tests/unit/test_dashboard_mission_api.py
git commit -m "feat: add mission detail operator view"
```

## Task 6: Implement Run Transcript UI

**Files:**
- Modify: `src/spec_orch/dashboard/static/operator-console.js`
- Modify: `src/spec_orch/dashboard/static/operator-console.css`
- Test: `tests/unit/test_dashboard_transcript_builder.py`

**Step 1: Write the failing test**

Add tests for transcript data shape used by UI:
- grouped command events
- milestone entries
- raw payload availability
- visual finding entries

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_transcript_builder.py -q
```

**Step 3: Write minimal implementation**

Build transcript split view:
- left timeline
- right inspector
- filters for packet / event type / severity
- collapsible stdout and tool payloads
- clear distinction between:
  - worker output
  - orchestrator events
  - supervisor decisions
  - visual evaluator findings

The default mode must be readable narrative, not raw JSON.

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_transcript_builder.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/static/operator-console.js src/spec_orch/dashboard/static/operator-console.css tests/unit/test_dashboard_transcript_builder.py
git commit -m "feat: add operator transcript view"
```

## Task 7: Add Inbox Scaffolding

**Files:**
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/static/operator-console.js`
- Test: `tests/unit/test_dashboard_inbox_api.py`

**Step 1: Write the failing test**

Add tests for `/api/inbox` covering:
- blocked missions
- ask-human items
- approval-needed items
- failed rounds

**Step 2: Run test to verify it fails**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_inbox_api.py -q
```

**Step 3: Write minimal implementation**

Create a lightweight inbox projection from:
- lifecycle states
- round decisions
- approval artifacts
- mission statuses

Only build enough to support the left-rail mode and top-priority triage list.

**Step 4: Run tests**

Run:
```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_inbox_api.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/api.py src/spec_orch/dashboard/static/operator-console.js tests/unit/test_dashboard_inbox_api.py
git commit -m "feat: add operator inbox api"
```

## Task 8: Docs and Verification

**Files:**
- Modify: `docs/agent-guides/services.md`
- Modify: `docs/agent-guides/run-pipeline.md`
- Modify: `docs/guides/supervised-mission-e2e-playbook.md`
- Modify: `README.md`

**Step 1: Update docs**

Document:
- new dashboard shell
- mission detail page
- transcript operator view
- inbox semantics

**Step 2: Run full verification**

Run:
```bash
uv run --python 3.13 python -m ruff check src/ tests/
uv run --python 3.13 python -m ruff format --check src/ tests/
uv run --python 3.13 python -m mypy src/
uv run --python 3.13 python -m pytest -q
uv run --python 3.13 python -c "print('build ok')"
```

**Step 3: Commit**

```bash
git add README.md docs/agent-guides/services.md docs/agent-guides/run-pipeline.md docs/guides/supervised-mission-e2e-playbook.md
git commit -m "docs: add operator console guidance"
```

## Recommended Execution Order

Implement in this order:

1. dashboard modularization
2. mission detail API
3. transcript API
4. operator shell
5. mission detail UI
6. transcript UI
7. inbox scaffolding
8. docs and verification

## Notes For The Implementer

- Reuse existing filesystem-first artifact model; do not invent a second telemetry store.
- Do not add React in this slice.
- Keep old endpoint names working where possible.
- Favor stable panes and split views over card dashboards.
- Every action exposed in UI must map to a real backend action or be visibly disabled.
- Transcript readability matters more than raw completeness in the default view.
