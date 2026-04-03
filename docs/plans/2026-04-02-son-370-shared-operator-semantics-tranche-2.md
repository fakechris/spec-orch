# SON-370 Shared Operator Semantics Tranche 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend shared operator semantics into the dashboard read-side by normalizing mission runtime chain and latest acceptance judgment into a canonical workspace snapshot.

**Architecture:** Keep existing dashboard payloads stable, but add a canonical `workspace` snapshot and shared `judgment` read models beside the legacy fields. Reuse the tranche 1 operator semantics domain objects and add adapters for `RuntimeChainStatus` plus a mission-level workspace builder so later execution/judgment workbench surfaces can consume one vocabulary.

**Tech Stack:** Python 3.13, dataclasses, existing runtime_chain and acceptance_core models, pytest unit tests.

### Task 1: Add runtime-chain-to-workspace adapters

**Files:**
- Modify: `src/spec_orch/services/operator_semantics.py`
- Test: `tests/unit/test_operator_semantics.py`

**Step 1: Write the failing tests**

Add tests for:
- `execution_session_from_runtime_chain_status()` mapping `RuntimeChainStatus` to `ExecutionSession`
- `workspace_from_mission_runtime()` producing a canonical mission workspace snapshot from runtime status and latest judgment

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `FAIL` because the new adapters do not exist yet.

**Step 2: Implement the minimal adapters**

Add:
- `execution_session_from_runtime_chain_status()`
- `workspace_from_mission_runtime()`

The workspace should:
- reuse `Workspace`, `ExecutionSession`, and `Judgment`
- preserve mission identity and title
- expose runtime-driven phase/health/reason text
- tolerate missing runtime or missing judgment by falling back to placeholders

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `PASS`.

### Task 2: Add shared workspace/judgment read models to dashboard payloads

**Files:**
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/surfaces.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Add tests that prove:
- mission detail now includes a canonical `workspace`
- acceptance-review payload now includes `shared_judgments`
- mission detail workspace uses runtime chain as active execution truth and latest shared judgment as active judgment truth

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because the dashboard readers do not yet emit the new shared payloads.

**Step 2: Implement the read-side integration**

Update:
- `_gather_mission_acceptance_review()` to append shared judgments derived from `judgment_from_acceptance_judgment()`
- `_gather_mission_detail()` to build and attach a canonical `workspace` snapshot using runtime chain status and latest shared judgment

Keep all existing legacy keys and shapes intact.

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_operator_semantics.py -q
```

Expected: `PASS`.

### Task 3: Verify the focused slice

**Files:**
- Verify only

**Step 1: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/operator_semantics.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/surfaces.py tests/unit/test_operator_semantics.py tests/unit/test_dashboard_api.py
```

Expected: all pass.

**Step 2: Decide gate scope**

If this tranche only changes read-side shaping and the focused tests are green, decide whether to stop at focused verification or rerun canonical acceptance based on how much mission detail/API behavior changed in practice.
