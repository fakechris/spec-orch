# Epic 2 and Epic 3 Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> 状态: completed on 2026-03-30

**Goal:** Finish `Epic 2: Runtime Core Extraction` and `Epic 3: Decision Core Extraction` from the current post-PR-162 baseline, so `runtime_core` and `decision_core` stop being partial scaffolds and become the canonical seams for runtime shaping and supervision state.

**Architecture:** `Epic 1` is already landed: shared execution semantics exist, normalized read/write carriers exist, and the first `runtime_core` / `decision_core` seams are live. The remaining work is not another semantic design pass. It is extraction completion: finish owner delegation into `runtime_core`, finish consumer cutover away from service-local shims, then expand `decision_core` from mission-round-only adoption into a repo-wide decision inventory plus review schema.

**Tech Stack:** Python 3.13, dataclasses, JSON/JSONL/Markdown carriers, existing `src/spec_orch` services/dashboard layout, pytest, ruff, incremental refactor with compatibility shims retained only where still necessary.

## Completion Summary

This plan is now complete.

Delivered:

- `runtime_core.adapters` as a real owner-facing seam
- mission leaf delegation for one-shot workers and packet executors
- consumer cutover from service-local execution shims to `runtime_core.readers`
- structural guard tests for runtime / decision core boundaries
- runtime-core boundary audit and updated migration matrix
- repo-wide `decision_core` inventory covering mission review, flow routing, conductor intent classification, and issue review verdicts
- `DecisionReview` plus file-backed review state in `decision_core.review_queue`

Verification completed with:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_runtime_core_imports.py tests/unit/test_runtime_core_paths.py tests/unit/test_runtime_core_readers.py tests/unit/test_runtime_core_writers.py tests/unit/test_runtime_core_structure.py tests/unit/test_decision_core_imports.py tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py tests/unit/test_decision_core_inventory.py tests/unit/test_decision_core_review_queue.py tests/unit/test_run_controller.py tests/unit/test_run_controller_flow.py tests/unit/test_round_orchestrator.py tests/unit/test_litellm_supervisor_adapter.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_missions.py tests/unit/test_dashboard_approvals.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py -v
```

Result: `231 passed`

## Current Baseline

Already landed in `main` via PR `#162` and follow-up fix `c586182`:

- `ExecutionAttempt`, `ExecutionOutcome`, `ArtifactRef`, `SupervisionCycle`
- `runtime_core/paths.py`, `runtime_core/readers.py`, `runtime_core/writers.py`
- `decision_core/models.py`, `decision_core/records.py`, `decision_core/review_queue.py`
- issue-path writer delegation
- ACPX worker + round supervision writer delegation
- mission supervision `DecisionRecord` writes
- approval queue reading `decision_core` intervention state

This plan starts from that baseline. Do not redo `Epic 1`.

## Epic 2 Remaining Scope

The remaining `Epic 2` work is:

- finish mission-leaf owner delegation (`E2-I5`)
- finish consumer cutover so normalized consumers read `runtime_core` directly (`E2-I7`)
- add structural guard tests (`E2-I8`)
- close the package-boundary audit (`E2-I9`)

`E2-I1` to `E2-I4` are effectively complete enough to treat as baseline.
`E2-I6` is substantially done and should only receive follow-up cleanup as part of `E2-I7`/`E2-I9`, not a separate redesign.

## Epic 3 Remaining Scope

The remaining `Epic 3` work is:

- expand `DecisionPoint` inventory beyond mission-round review (`E3-I5`)
- add `DecisionReview` schema and file-backed review state (`E3-I6`)

`E3-I1` to `E3-I4` are the baseline.

## Task 1: Finish Mission-Leaf Owner Delegation (`E2-I5`)

**Files:**
- Modify: `src/spec_orch/services/workers/oneshot_worker_handle.py`
- Modify: `src/spec_orch/services/packet_executor.py`
- Modify: `src/spec_orch/runtime_core/adapters.py`
- Modify: `src/spec_orch/runtime_core/writers.py`
- Create: `tests/unit/test_oneshot_worker_handle.py`
- Create or Modify: `tests/unit/test_packet_executor.py`
- Modify: `tests/unit/test_runtime_core_writers.py`

**Step 1: Write failing tests**

Cover:
- one-shot worker path delegates normalized payload shaping through `runtime_core`
- packet executor paths do not hand-roll normalized writer targets in owner code

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_oneshot_worker_handle.py tests/unit/test_packet_executor.py -v
```

Expected: FAIL with missing tests or owner-local shaping still visible.

**Step 2: Add runtime-core owner-facing adapters**

Add explicit owner-facing helpers in `runtime_core/adapters.py`, for example:
- `write_issue_attempt_payloads(...)`
- `write_worker_attempt_payloads(...)`
- `write_round_cycle_payloads(...)`

Do not leave `runtime_core/adapters.py` empty once this task is complete.

**Step 3: Route mission leaf owners through adapters**

- `OneShotWorkerHandle` should stop being a pure pass-through for persistence semantics.
- `packet_executor.py` should use runtime-core adapters for normalized payload shaping wherever packet execution emits canonical artifacts.

**Step 4: Run targeted verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_oneshot_worker_handle.py tests/unit/test_packet_executor.py tests/unit/test_runtime_core_writers.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/workers/oneshot_worker_handle.py src/spec_orch/services/packet_executor.py src/spec_orch/runtime_core/adapters.py src/spec_orch/runtime_core/writers.py tests/unit/test_oneshot_worker_handle.py tests/unit/test_packet_executor.py tests/unit/test_runtime_core_writers.py
git commit -m "refactor: finish mission leaf delegation into runtime core"
```

## Task 2: Cut Consumers Over to `runtime_core` Facades (`E2-I7`)

**Files:**
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/surfaces.py`
- Modify: `src/spec_orch/dashboard/transcript.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Modify: `src/spec_orch/services/evidence_analyzer.py`
- Modify: `src/spec_orch/services/eval_runner.py`
- Modify: `src/spec_orch/services/execution_semantics_reader.py`
- Modify: `src/spec_orch/services/execution_semantics_writer.py`
- Modify: `tests/unit/test_dashboard_api.py`
- Modify: `tests/unit/test_dashboard_missions.py`
- Modify: `tests/unit/test_context_assembler.py`
- Modify: `tests/unit/test_evidence_analyzer.py`
- Modify: `tests/unit/test_eval_runner.py`

**Step 1: Write failing seam-ownership tests**

Add tests that prove:
- runtime consumers import from `runtime_core` or `runtime_core.adapters`
- service shims remain compatibility wrappers only

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_missions.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py -v
```

Expected: FAIL once assertions for direct `runtime_core` usage are added.

**Step 2: Replace shim usage in consumers**

Consumers should stop importing:
- `spec_orch.services.execution_semantics_reader`
- `spec_orch.services.execution_semantics_writer`

unless they are explicitly compatibility-only surfaces.

Prefer:
- `spec_orch.runtime_core.readers`
- `spec_orch.runtime_core.adapters`

**Step 3: Reduce service shims to strict compatibility bridges**

- `services/execution_semantics_reader.py`
- `services/execution_semantics_writer.py`

These modules should contain no business logic after this task, only forwards/re-exports.

**Step 4: Run verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_missions.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_runtime_core_readers.py tests/unit/test_runtime_core_writers.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/control.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/surfaces.py src/spec_orch/dashboard/transcript.py src/spec_orch/services/context/context_assembler.py src/spec_orch/services/evidence_analyzer.py src/spec_orch/services/eval_runner.py src/spec_orch/services/execution_semantics_reader.py src/spec_orch/services/execution_semantics_writer.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_missions.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py
git commit -m "refactor: cut consumers over to runtime core facades"
```

## Task 3: Add Structural Guard Tests (`E2-I8`)

**Files:**
- Create: `tests/unit/test_runtime_core_structure.py`
- Modify: `tests/unit/test_runtime_core_imports.py`
- Modify: `tests/unit/test_decision_core_imports.py`

**Step 1: Write failing guard tests**

Add assertions for:
- no normalized payload path helpers in owners outside `runtime_core.paths`
- no normalized writer JSON construction in owner-local modules already migrated
- `runtime_core/adapters.py` is non-empty and exports the intended seam

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_runtime_core_structure.py tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py -v
```

Expected: FAIL until the structure checks are in place.

**Step 2: Implement minimal structure checks**

Use simple import/assertion tests. Do not build a custom lint framework here.

**Step 3: Run verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_runtime_core_structure.py tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add tests/unit/test_runtime_core_structure.py tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py
git commit -m "test: add runtime and decision core structure guards"
```

## Task 4: Close Runtime-Core Boundary Audit (`E2-I9`)

**Files:**
- Create: `docs/architecture/2026-03-30-runtime-core-boundary-audit.md`
- Modify: `docs/architecture/core-extraction-migration-matrix.md`

**Step 1: Audit remaining leaks**

Explicitly classify:
- migrated owners
- remaining compatibility shims
- intentional bridge files
- unresolved leaks to defer into later epics

**Step 2: Update migration matrix**

Mark each relevant module as one of:
- `done`
- `bridge`
- `follow-up`

**Step 3: Commit**

```bash
git add docs/architecture/2026-03-30-runtime-core-boundary-audit.md docs/architecture/core-extraction-migration-matrix.md
git commit -m "docs: close runtime core boundary audit"
```

## Task 5: Expand Decision Inventory to Non-Mission Paths (`E3-I5`)

**Files:**
- Modify: `src/spec_orch/decision_core/models.py`
- Modify: `src/spec_orch/decision_core/records.py`
- Create: `src/spec_orch/decision_core/inventory.py`
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/services/conductor/conductor.py`
- Modify: `src/spec_orch/services/flow_router.py`
- Modify: `src/spec_orch/services/review_adapter.py`
- Modify: `tests/unit/test_decision_core_models.py`
- Modify: `tests/unit/test_decision_core_records.py`
- Create: `tests/unit/test_decision_core_inventory.py`

**Step 1: Write failing inventory tests**

Inventory must at minimum classify:
- issue/run path LLM decisions
- review adapter decisions
- flow/router fallback decisions
- conductor intent/classification decisions

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py tests/unit/test_decision_core_inventory.py -v
```

Expected: FAIL because the non-mission inventory is not yet represented.

**Step 2: Add explicit inventory module**

`decision_core/inventory.py` should expose canonical point definitions and grouping helpers.

Do not leave the inventory implicit in scattered services.

**Step 3: Thread point keys into non-mission decision owners**

Minimal adoption only:
- enough metadata to identify each owner/path
- no broad review queue migration yet

**Step 4: Run verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py tests/unit/test_decision_core_inventory.py tests/unit/test_run_controller.py tests/unit/test_run_controller_flow.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/decision_core/models.py src/spec_orch/decision_core/records.py src/spec_orch/decision_core/inventory.py src/spec_orch/services/run_controller.py src/spec_orch/services/conductor/conductor.py src/spec_orch/services/flow_router.py src/spec_orch/services/review_adapter.py tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py tests/unit/test_decision_core_inventory.py tests/unit/test_run_controller.py tests/unit/test_run_controller_flow.py
git commit -m "feat: expand decision inventory beyond mission supervision"
```

## Task 6: Add `DecisionReview` Schema and Review State (`E3-I6`)

**Files:**
- Modify: `src/spec_orch/decision_core/models.py`
- Modify: `src/spec_orch/decision_core/review_queue.py`
- Create: `tests/unit/test_decision_core_review_queue.py`
- Modify: `tests/unit/test_decision_core_models.py`
- Modify: `tests/unit/test_dashboard_approvals.py`

**Step 1: Write failing tests**

Cover:
- `DecisionReview` dataclass
- human review outcome fields
- self-review / reflection fields
- escalation judgment fields
- file-backed review append/load helpers

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_decision_core_models.py tests/unit/test_decision_core_review_queue.py tests/unit/test_dashboard_approvals.py -v
```

Expected: FAIL because review schema/path does not exist yet.

**Step 2: Add `DecisionReview`**

Minimum shape:
- `review_id`
- `record_id`
- `reviewer_kind`
- `verdict`
- `summary`
- `recommended_authority`
- `escalate_to_human`
- `created_at`

**Step 3: Add review queue persistence**

Add file-backed helpers adjacent to intervention state. Do not bury this in `memory` yet.

**Step 4: Run verification**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_decision_core_models.py tests/unit/test_decision_core_review_queue.py tests/unit/test_dashboard_approvals.py tests/unit/test_litellm_supervisor_adapter.py tests/unit/test_round_orchestrator.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/decision_core/models.py src/spec_orch/decision_core/review_queue.py tests/unit/test_decision_core_models.py tests/unit/test_decision_core_review_queue.py tests/unit/test_dashboard_approvals.py tests/unit/test_litellm_supervisor_adapter.py tests/unit/test_round_orchestrator.py
git commit -m "feat: add decision review schema and persistence"
```

## Task 7: Epic 2/3 Final Validation and PR Cut

**Files:**
- Create: `docs/plans/2026-03-30-epic-2-3-validation-and-pr-cut.md`

**Step 1: Run full Epic 2/3 validation suite**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_runtime_core_imports.py tests/unit/test_runtime_core_paths.py tests/unit/test_runtime_core_readers.py tests/unit/test_runtime_core_writers.py tests/unit/test_runtime_core_structure.py tests/unit/test_decision_core_imports.py tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py tests/unit/test_decision_core_inventory.py tests/unit/test_decision_core_review_queue.py tests/unit/test_run_controller.py tests/unit/test_run_controller_flow.py tests/unit/test_round_orchestrator.py tests/unit/test_litellm_supervisor_adapter.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_missions.py tests/unit/test_dashboard_approvals.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py -v
```

Expected: PASS

**Step 2: Run lint/type checks**

```bash
uv run --python 3.13 ruff check src/ tests/
uv run --python 3.13 ruff format --check src/ tests/
uv run --python 3.13 mypy src/spec_orch/
```

Expected: PASS

**Step 3: Write PR cut doc**

Capture:
- completed issues
- intentionally deferred follow-ups
- merge criteria

**Step 4: Commit**

```bash
git add docs/plans/2026-03-30-epic-2-3-validation-and-pr-cut.md
git commit -m "docs: record epic 2 and 3 validation cut"
```

## Recommended Execution Order

1. Task 1: Mission-leaf owner delegation
2. Task 2: Consumer cutover
3. Task 3: Structural guard tests
4. Task 4: Runtime-core boundary audit
5. Task 5: Non-mission decision inventory
6. Task 6: Decision review schema
7. Task 7: Final validation and PR cut

## Stop Conditions

Do not call `Epic 2` done until:

- owner-local normalized write shaping is out of the remaining mission leaf owners
- primary consumers read `runtime_core` directly
- structure guards exist
- boundary audit is written

Do not call `Epic 3` done until:

- decision inventory includes non-mission owners
- `DecisionReview` exists as a first-class object
- decision review persistence exists outside ad hoc dashboard state

Plan complete and saved to `docs/plans/2026-03-30-epic-2-3-completion-plan.md`.
