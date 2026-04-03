# SON-374 Runtime and Execution Substrate Tranche 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the execution substrate from a bare runtime inventory into a pressure-aware read model that surfaces queue, intervention, and admission posture for operator-visible execution control.

**Architecture:** Keep the tranche read-only. Reuse existing mission operator artifacts instead of inventing new daemon state: `interventions.jsonl` and intervention response history become queue/intervention records, while observability `live_summary.json` files become runtime pressure signals. Aggregate those sources into the existing execution substrate snapshot and expose them through the control overview without changing existing dashboard routes.

**Tech Stack:** Python 3.13, dataclasses, runtime_chain store, runtime_core observability models, decision_core review queue artifacts, dashboard control API, pytest unit tests.

### Task 1: Add failing substrate tests for queue and pressure

**Files:**
- Modify: `tests/unit/test_execution_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add tests that prove:
- open mission interventions become `queue` entries and `interventions`
- runtime observability live summaries become runtime pressure/budget signals
- runtime usage/activity summaries expose admission posture counts derived from current runtime state
- `/api/control/overview` returns the richer substrate unchanged through the API

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the substrate does not yet read intervention queues or observability pressure.

### Task 2: Implement queue, intervention, and pressure readers

**Files:**
- Modify: `src/spec_orch/services/execution_substrate.py`

**Step 1: Implement minimal readers**

Add read helpers for:
- `docs/specs/*/operator/interventions.jsonl`
- `docs/specs/*/operator/intervention_responses.jsonl`
- `docs/specs/*/operator/observability/*/live_summary.json`

Map them into substrate carriers:
- `QueueEntry`
- `OperatorIntervention`
- runtime `usage_summary` and `activity_summary`

Admission posture should remain a conservative read model:
- `admit_count` from active/healthy runtime work
- `defer_count` from queued intervention items
- `degrade_count` from degraded runtime work
- `reject_count` from failed runtime work

Do not introduce enforcement or write new runtime artifacts in this tranche.

**Step 2: Run the focused tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `PASS`.

### Task 3: Verify serialization and lint cleanliness

**Files:**
- Modify if needed: `tests/unit/test_operator_semantics.py`

**Step 1: Extend coverage only if needed**

If the new snapshot shape depends on additional carrier serialization expectations, add a small focused test; otherwise keep model tests untouched.

**Step 2: Run verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/execution_substrate.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py tests/unit/test_operator_semantics.py
```

Expected: all pass.

### Task 4: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

Because the change alters operator-visible control overview state and execution substrate semantics, rerun canonical acceptance at tranche close.

**Step 2: Archive the tranche**

If canonical acceptance stays green, write a new release bundle and refresh the rolling acceptance-history index with source-run compare notes versus the prior `SON-374` bundle.
