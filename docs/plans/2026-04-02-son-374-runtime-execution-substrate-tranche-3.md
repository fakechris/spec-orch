# SON-374 Runtime and Execution Substrate Tranche 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the v1 execution substrate by promoting queue, pressure, admission, session, and event state into explicit canonical read models that the operator control plane can consume directly.

**Architecture:** Keep the tranche read-only and artifact-backed. Reuse `runtime_chain` status/events, mission intervention logs, and observability summaries as the single source of truth. Promote those records into shared operator-semantics carriers so `control/overview` no longer depends on inferred counters alone. This tranche intentionally stops short of daemon-side enforcement; it finishes the substrate contract that `SON-412` and the Execution Workbench will consume.

**Tech Stack:** Python 3.13, dataclasses, runtime_chain store, runtime_core observability models, dashboard control API, pytest unit tests.

### Task 1: Add failing substrate tests for explicit runtime carriers

**Files:**
- Modify: `tests/unit/test_execution_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add focused tests that prove:
- `build_execution_substrate_snapshot()` returns explicit `admission_decisions`
- the snapshot returns canonical `resource_budgets` and `pressure_signals`
- runtime-chain events become operator-readable `execution_events`
- runtime-chain statuses become canonical `execution_sessions`
- `/api/control/overview` passes the richer substrate through unchanged

**Step 2: Run the failing tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the substrate does not yet emit those explicit carriers.

### Task 2: Implement the remaining execution substrate contract

**Files:**
- Modify: `src/spec_orch/domain/operator_semantics.py`
- Modify: `src/spec_orch/services/execution_substrate.py`
- Modify: `src/spec_orch/dashboard/control.py`

**Step 1: Add canonical carrier models**

Add shared operator semantics for:
- `ResourceBudget`
- `PressureSignal`
- `AdmissionDecision`
- `ExecutionEvent`

Keep the fields aligned with the `SON-412` concurrency/admission contract and the Execution Workbench contract.

**Step 2: Populate the carriers from existing artifacts**

Use:
- `runtime_chain/chain_status.json`
- `runtime_chain/chain_events.jsonl`
- `operator/interventions.jsonl`
- `operator/intervention_responses.jsonl`
- `operator/observability/*/live_summary.json`

Map them into:
- canonical `execution_sessions`
- canonical `execution_events`
- canonical `resource_budgets`
- canonical `pressure_signals`
- canonical `admission_decisions`

Do not add daemon writes or scheduling enforcement in this tranche.

**Step 3: Re-run the focused tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `PASS`.

### Task 3: Verify lint and broader substrate compatibility

**Files:**
- Modify if needed: `tests/unit/test_operator_semantics.py`

**Step 1: Add compatibility coverage only if needed**

If the new carriers require a small serialization coverage test, add one focused test and stop there.

**Step 2: Run verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/domain/operator_semantics.py src/spec_orch/services/execution_substrate.py src/spec_orch/dashboard/control.py tests/unit/test_operator_semantics.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

### Task 4: Tranche gate and archive

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run canonical acceptance**

This tranche changes operator-visible execution contracts, so rerun the canonical acceptance suite at close.

**Step 2: Archive the tranche**

If acceptance stays green, write a new `SON-374` release bundle and refresh the rolling acceptance-history index with source-run compare notes versus the prior `SON-374` bundle.
