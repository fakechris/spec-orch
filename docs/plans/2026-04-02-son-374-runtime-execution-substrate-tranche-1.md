# SON-374 Runtime and Execution Substrate Tranche 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce canonical runtime, agent, and active-work carriers, then expose a first execution substrate inventory through the control overview API.

**Architecture:** Finish the execution-side shared vocabulary in `operator_semantics`, add a small `execution_substrate` read service that scans current runtime-chain truth across issue and mission workspaces, and attach its inventory to `/api/control/overview`. Keep queue and intervention records present as explicit empty carriers until later substrate slices own them.

**Tech Stack:** Python 3.13, dataclasses, existing runtime_chain store, dashboard control API, pytest unit tests.

### Task 1: Add execution substrate domain carriers

**Files:**
- Modify: `src/spec_orch/domain/operator_semantics.py`
- Test: `tests/unit/test_operator_semantics.py`

**Step 1: Write the failing tests**

Add tests for canonical execution-side models:
- `Agent`
- `Runtime`
- `ActiveWork`
- `QueueEntry`
- `OperatorIntervention`

The test should assert operator-facing fields and `to_dict()` output.

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `FAIL` because the new models do not exist yet.

**Step 2: Implement the minimal models**

Add the canonical dataclasses with stable field names from the execution contract docs. Keep them serialization-only in this tranche.

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `PASS`.

### Task 2: Build execution substrate inventory service

**Files:**
- Create: `src/spec_orch/services/execution_substrate.py`
- Test: `tests/unit/test_execution_substrate.py`

**Step 1: Write the failing tests**

Add tests that prove:
- mission runtime-chain status becomes `ActiveWork`, `Agent`, and `Runtime`
- issue runtime-chain status also participates in the same inventory
- the substrate summary reports running/degraded/intervention-needed counts
- queue and interventions are explicit arrays even when empty

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py -q
```

Expected: `FAIL` because the service does not exist yet.

**Step 2: Implement the substrate reader**

Create:
- runtime-chain discovery across `docs/specs/*/operator/runtime_chain`
- issue discovery across `.worktrees/*/telemetry/runtime_chain`
- adapters from `RuntimeChainStatus` to:
  - `ActiveWork`
  - `Agent`
  - `Runtime`

Return:
- `summary`
- `active_work`
- `agents`
- `runtimes`
- `queue`
- `interventions`

Use conservative placeholders where data is not yet owned canonically.

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_execution_substrate.py -q
```

Expected: `PASS`.

### Task 3: Expose the substrate through control overview

**Files:**
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Extend the failing tests**

Add tests showing:
- `/api/control/overview` includes `execution_substrate`
- the substrate summary and inventories are populated from runtime-chain truth

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_execution_substrate.py tests/unit/test_operator_semantics.py -q
```

Expected: `FAIL` because control overview does not yet expose the substrate.

**Step 2: Implement the integration**

Update `_control_overview()` to include the substrate payload returned by the new service. Do not remove any existing control-overview keys.

**Step 3: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/domain/operator_semantics.py src/spec_orch/services/operator_semantics.py src/spec_orch/services/execution_substrate.py src/spec_orch/dashboard/control.py tests/unit/test_operator_semantics.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

### Task 4: Decide gate and archive scope

**Files:**
- Modify if needed: `.spec_orch/acceptance/stability_acceptance_status.json`
- Modify if needed: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Decide whether to run canonical acceptance**

If the change remains a read-side/API addition with existing routes preserved, focused verification may be sufficient. If any dashboard or runtime inventory route behavior shifts materially, rerun canonical acceptance and archive the tranche.
