# Dashboard Mission Launcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let an operator create, approve, plan, bind, and launch a supervised mission from the dashboard without editing files or manually touching Linear issue descriptions.

**Architecture:** Add a thin dashboard-first launcher layer on top of existing `MissionService`, planning, promotion, and lifecycle services. Keep the current operator console as the runtime workbench, but prepend a mission-setup workflow with API endpoints, readiness checks, and a lightweight launcher panel. Do not invent a parallel mission system; wrap existing services.

**Tech Stack:** FastAPI dashboard routes, existing mission/planning services, Linear GraphQL client, operator-console JS/CSS, pytest, ruff, mypy.

## Context

Today the runtime operator console is strong, but the launch path is too manual:

- create mission via CLI
- edit `docs/specs/<mission_id>/spec.md`
- run `spec-orch mission approve`
- run `spec-orch plan`
- create/edit a Linear issue manually and add `mission: <mission_id>`
- start daemon

The product gap is not evidence or observability. The gap is launch ergonomics.

## Scope

This slice should deliver the smallest useful dashboard-first launch flow:

1. Environment readiness panel
2. Mission draft creation from dashboard
3. Approve + plan from dashboard
4. Linear issue create/bind from dashboard
5. Mission launch action from dashboard

This slice does **not** need:

- a rich multi-step wizard framework
- full inline spec markdown editor
- final visual polish
- replacement of the existing daemon

## Task 1: Launcher service module

**Files:**
- Create: `src/spec_orch/dashboard/launcher.py`
- Modify: `src/spec_orch/dashboard/__init__.py`
- Test: `tests/unit/test_dashboard_launcher.py`

**Step 1: Write the failing tests**

Cover:

- readiness reports missing Linear token / planner config / dashboard config
- mission draft creation writes `mission.json` and `spec.md`
- approve + plan writes `plan.json`
- bind/create Linear issue returns issue metadata and includes `mission: <id>`
- launch action returns lifecycle state when available

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_launcher.py -q
```

Expected:
- import or attribute failures because launcher module does not exist yet

**Step 3: Write minimal implementation**

Implement a small launcher helper module that exposes:

- `_gather_launcher_readiness(root: Path) -> dict[str, Any]`
- `_create_mission_draft(root: Path, payload: dict[str, Any]) -> dict[str, Any]`
- `_approve_and_plan_mission(root: Path, mission_id: str) -> dict[str, Any]`
- `_create_linear_issue_for_mission(root: Path, mission_id: str, title: str, description: str) -> dict[str, Any]`
- `_bind_linear_issue_to_mission(root: Path, mission_id: str, linear_issue_id: str) -> dict[str, Any]`
- `_launch_mission(root: Path, mission_id: str) -> dict[str, Any]`

Rules:

- use `MissionService` for mission create/approve
- reuse the planning path already implemented in `cli/mission_commands.py`
- use `LinearClient` directly for issue creation/update
- use lifecycle manager for launch
- store mission-bound Linear metadata in a small dashboard-friendly file under `docs/specs/<mission_id>/operator/launch.json`

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_launcher.py -q
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/launcher.py src/spec_orch/dashboard/__init__.py tests/unit/test_dashboard_launcher.py
git commit -m "feat: add dashboard mission launcher service"
```

## Task 2: Dashboard routes for launcher

**Files:**
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/api.py`
- Modify: `src/spec_orch/dashboard/__init__.py`
- Test: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add API tests for:

- `GET /api/launcher/readiness`
- `POST /api/launcher/missions`
- `POST /api/launcher/missions/{mission_id}/approve-plan`
- `POST /api/launcher/missions/{mission_id}/linear-create`
- `POST /api/launcher/missions/{mission_id}/linear-bind`
- `POST /api/launcher/missions/{mission_id}/launch`

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q -k launcher
```

**Step 3: Write minimal implementation**

Add routes that delegate to the launcher helpers and return JSON payloads only.

Contracts:

- no CLI shell-outs
- no file editing from the browser
- consistent error JSON:
  - `{"error": "..."}`
- mission creation payload should accept:
  - `title`
  - `mission_id` (optional)
  - `intent`
  - `acceptance_criteria`
  - `constraints`

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q -k launcher
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/api.py src/spec_orch/dashboard/__init__.py tests/unit/test_dashboard_api.py
git commit -m "feat: expose mission launcher dashboard APIs"
```

## Task 3: Minimal launcher UI in dashboard shell

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/dashboard/shell.py`
- Modify: `src/spec_orch/dashboard_assets/static/operator-console.js`
- Modify: `src/spec_orch/dashboard_assets/static/operator-console.css`
- Test: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing test**

Assert homepage now contains launcher surface anchors:

- `id="mission-launcher-panel"`
- `id="launcher-readiness"`
- `id="launcher-form"`
- `id="launcher-linear-panel"`

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q -k homepage
```

**Step 3: Write minimal implementation**

Add a small launcher panel in the left rail or top of the main canvas:

- readiness summary
- create mission form
- approve + plan button
- create Linear issue button
- bind existing issue field
- launch mission button

Keep it simple:

- no modal
- no multi-page wizard
- no markdown editor

Use existing operator-console styles; add only the minimum new classes needed.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q -k homepage
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/app.py src/spec_orch/dashboard/shell.py src/spec_orch/dashboard_assets/static/operator-console.js src/spec_orch/dashboard_assets/static/operator-console.css tests/unit/test_dashboard_api.py
git commit -m "feat: add dashboard mission launcher panel"
```

## Task 4: Launcher docs refresh

**Files:**
- Modify: `docs/guides/operator-console.md`
- Modify: `docs/guides/supervised-mission-e2e-playbook.md`
- Modify: `docs/agent-guides/services.md`

**Step 1: Write docs assertions**

Manually verify the docs mention:

- dashboard-first mission creation
- dashboard readiness
- create/bind Linear issue from dashboard
- launch from dashboard

**Step 2: Write minimal docs updates**

Update the guides so the preferred flow is:

- open dashboard
- create mission
- approve + plan
- create/bind Linear issue
- launch

Move CLI-first setup to fallback / advanced path.

**Step 3: Verify docs references**

Run:

```bash
rg -n "launcher|Approve & Plan|Create Linear Issue|Bind Existing Issue|Launch Mission" docs/guides/operator-console.md docs/guides/supervised-mission-e2e-playbook.md docs/agent-guides/services.md
```

**Step 4: Commit**

```bash
git add docs/guides/operator-console.md docs/guides/supervised-mission-e2e-playbook.md docs/agent-guides/services.md
git commit -m "docs: document dashboard mission launcher flow"
```

## Task 5: Full verification

**Files:**
- Modify: none expected

**Step 1: Run dashboard-focused verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_launcher.py tests/unit/test_dashboard_package.py -q
```

**Step 2: Run full repo verification**

```bash
uv run --python 3.13 python -m ruff check src/ tests/
uv run --python 3.13 python -m ruff format --check src/ tests/
uv run --python 3.13 python -m mypy src/
uv run --python 3.13 python -m pytest -q
uv run --python 3.13 python -c "print('build ok')"
```

**Step 3: Manual smoke**

Run:

```bash
export SPEC_ORCH_LINEAR_TOKEN="$LINEAR_TOKEN"
uv run --python 3.13 spec-orch dashboard --host 127.0.0.1 --port 8420
```

Verify:

- launcher panel renders
- readiness displays
- create mission works
- approve + plan works
- Linear create/bind works
- launch action updates mission state

**Step 4: Commit**

```bash
git status --short
```

Only commit if anything changed during verification fixes.

## Notes

- Prefer adding a launcher module over bloating `routes.py` or `app.py`
- Reuse service-layer logic instead of shelling out to CLI commands
- Keep the first slice minimal: good enough to remove file-edit + manual Linear binding from the happy path
