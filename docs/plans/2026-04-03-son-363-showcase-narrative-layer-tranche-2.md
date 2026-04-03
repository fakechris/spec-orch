# SON-363 Showcase / Narrative Layer Tranche 2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the global showcase surface so operators can read release lineage and governance drilldowns directly from the showcase UI, not just from the service/API payload.

**Architecture:** Keep showcase downstream-only. This tranche may consume `docs/acceptance-history` bundles plus the canonical execution, judgment, and learning workbenches, but it must not introduce new write paths or a competing store.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff, mypy

### Task 1: Lock the showcase rendering contract in tests

**Files:**
- Modify: `tests/unit/test_showcase_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`
- Modify: `tests/unit/test_dashboard_package.py`

**Step 1: Write the failing tests**

Require:
- release timeline rows to expose `workspace_ids` and `lineage_notes`
- workspace storylines to expose `governance_story` and `lineage_drilldown`
- the dashboard shell source to render linked workspaces, lineage notes, governance story, promotion decision, and latest release notes

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_dashboard_package.py -q -k showcase_surface_renders_governance_and_lineage_fields
```

Expected: `FAIL` because `app.py` does not yet consume the new showcase carriers.

### Task 2: Implement minimal showcase UI exposure

**Files:**
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/services/showcase_workbench.py`

**Step 1: Implement the tranche**

Implement:
- release timeline cards that show linked workspaces and lineage notes
- workspace storyline cards that show governance story and latest release notes
- showcase context rail summaries that expose the same lineage/governance carriers

Keep:
- showcase as a read model only
- mission-local tabs unchanged
- rendering minimal and textual; no new interaction surfaces in this tranche

**Step 2: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_dashboard_package.py -q -k showcase_surface_renders_governance_and_lineage_fields
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py -q -k showcase
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/dashboard/app.py src/spec_orch/services/showcase_workbench.py tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/showcase_workbench.py
```

Expected: `PASS`

### Task 3: Tranche closeout

**Step 1: Decide whether this tranche is UI-only or requires formal acceptance**

If the change remains strictly showcase read-side and does not affect canonical workflow behavior, focused verification is sufficient before commit.

If the tranche grows to affect dashboard mission flows or artifact routing, rerun canonical acceptance and write a new release bundle.

**Step 2: Preserve release/archive discipline if acceptance is rerun**

If acceptance is rerun for this tranche:
- refresh `docs/plans/2026-03-30-stability-acceptance-status.md`
- write a new bundle under `docs/acceptance-history/releases/`
- refresh `docs/acceptance-history/index.json`
