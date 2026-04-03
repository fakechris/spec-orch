# SON-379 Decision and Judgment Substrate Tranche 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote acceptance-review outputs into a canonical judgment substrate so dashboard consumers can read `EvidenceBundle`, `JudgmentTimelineEntry`, `CompareOverlay`, and `SurfacePack` carriers instead of reconstructing judgment semantics in page code.

**Architecture:** Keep the tranche read-only. Reuse existing acceptance-review artifacts, candidate-finding ontology, surface-pack calibration helpers, and shared operator semantics. Add a judgment substrate service that reads mission round artifacts and emits canonical judgment-side carriers for acceptance-review routes, while preserving the existing API shape for current dashboard consumers.

**Tech Stack:** Python 3.13, dataclasses, acceptance_core models/disposition/calibration, dashboard acceptance review surface, pytest unit tests.

### Task 1: Add failing substrate tests for canonical judgment carriers

**Files:**
- Create: `tests/unit/test_judgment_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add focused tests that prove:
- an acceptance review becomes a canonical `EvidenceBundle`
- judgment timeline events are emitted for routing, evidence, compare, and judgment state
- compare overlay state is surfaced explicitly
- surface pack metadata is surfaced explicitly
- `/api/missions/:id/acceptance-review` exposes those canonical carriers without breaking current fields

**Step 2: Run the failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the canonical judgment substrate service does not yet exist.

### Task 2: Implement the judgment substrate

**Files:**
- Modify: `src/spec_orch/domain/operator_semantics.py`
- Create: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/dashboard/surfaces.py`

**Step 1: Add canonical judgment-side carriers**

Add shared operator semantics for:
- `JudgmentTimelineEntry`
- `CompareOverlay`
- `SurfacePack`

Keep the fields aligned with the Judgment Workbench contract.

**Step 2: Build the substrate service**

Implement a service that:
- reads mission acceptance-review artifacts round-by-round
- normalizes `AcceptanceReviewResult` into canonical `Judgment` objects
- emits `EvidenceBundle`, `JudgmentTimelineEntry`, `CompareOverlay`, and `SurfacePack`
- preserves existing acceptance-review summary fields for current dashboard consumers

**Step 3: Switch dashboard acceptance-review gathering to use the substrate**

Keep `/api/missions/:id/acceptance-review` backward compatible, but make it source its judgment semantics from the substrate service rather than hand-built page logic.

### Task 3: Verify substrate compatibility

**Files:**
- Modify if needed: `tests/unit/test_operator_semantics.py`

**Step 1: Add a small serialization test only if needed**

If the new carriers need direct shared-semantics serialization coverage, add one focused test and stop there.

**Step 2: Run verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/domain/operator_semantics.py src/spec_orch/services/judgment_substrate.py src/spec_orch/dashboard/surfaces.py tests/unit/test_operator_semantics.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

### Task 4: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

This tranche changes operator-visible judgment semantics, so rerun canonical acceptance at close.

**Step 2: Archive the tranche**

If acceptance stays green, write a new `SON-379` release bundle and refresh the rolling acceptance-history index with source-run compare notes versus the final `SON-374` bundle.
