# Runtime Extraction Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** After shared execution semantics exist, extract a visible runtime core so the codebase is no longer “multiple owners writing similar payloads in parallel,” but a system with explicit read/write seams and clearer program organization.

**Architecture:** Phase 1 gives the codebase a shared semantic vocabulary. Phase 2 makes that vocabulary structurally real by introducing a dedicated runtime-core package, routing all normalized reads/writes through it, and making issue/mission owners delegate to that seam instead of each hand-rolling persistence and interpretation logic. This phase still preserves separate owners and closure locations; it extracts organization, not final owner unification.

**Tech Stack:** Python 3.13, dataclasses, existing services/ dashboard layout, JSON/JSONL artifact files, pytest unit tests, incremental refactor with dual-write retained.

## What Phase 2 Is Solving

Phase 1 alone is not enough.
Even with shared semantics, the codebase can still remain structurally ambiguous:

- `RunController` still writes one shape
- mission workers still write another
- `RoundOrchestrator` still writes a third
- readers may start using similar names without sharing a real seam

That creates a dangerous “half-unified” state:

- semantics sound shared
- ownership is still scattered
- code organization still teaches the wrong mental model

Phase 2 exists to prevent that outcome.

## Non-Goals

This phase does **not**:

- merge `RunController` and `RoundOrchestrator`
- merge `Mission` and `Issue`
- eliminate legacy files in one shot
- change closure location (`issue` remains leaf-owned, `Mission` remains round-owned)

## Target End State

By the end of Phase 2:

1. There is a clearly visible runtime-core package for normalized execution semantics.
2. All normalized readers go through runtime-core, not ad hoc file-name branching.
3. All normalized writers go through runtime-core, not owner-local JSON construction.
4. Dashboard, analytics, context assembly, and replay tooling depend on the runtime-core seam.
5. Owners remain distinct, but the code organization now exposes the shared layer explicitly.

## Proposed Program Organization

Introduce a new package:

```text
src/spec_orch/runtime_core/
  __init__.py
  models.py
  paths.py
  readers.py
  writers.py
  supervision.py
  adapters.py
```

Responsibilities:

- `models.py`
  - normalized `ExecutionAttempt`, `ExecutionOutcome`, `ArtifactRef`, `SupervisionCycleRef`
- `paths.py`
  - canonical normalized file/directory locations
- `readers.py`
  - normalized readers from current issue / mission artifacts
- `writers.py`
  - normalized writers for issue leaf, mission leaf, mission round
- `supervision.py`
  - helpers specific to round-level supervision payloads
- `adapters.py`
  - thin owner-facing bridges so owners do not construct normalized payloads themselves

Important rule:

- runtime-core owns normalized interpretation and normalized persistence
- owners own execution and lifecycle

## Task 1: Create Runtime-Core Package Skeleton

**Files:**
- Create: `src/spec_orch/runtime_core/__init__.py`
- Create: `src/spec_orch/runtime_core/models.py`
- Create: `src/spec_orch/runtime_core/paths.py`
- Create: `src/spec_orch/runtime_core/readers.py`
- Create: `src/spec_orch/runtime_core/writers.py`
- Create: `src/spec_orch/runtime_core/supervision.py`
- Create: `src/spec_orch/runtime_core/adapters.py`
- Test: `tests/unit/test_runtime_core_imports.py`

**Step 1: Write failing import tests**

Run:

```bash
pytest tests/unit/test_runtime_core_imports.py -v
```

Expected: FAIL with missing package/modules.

**Step 2: Create package and re-export semantic models**

Initially, `models.py` may wrap or re-export Phase 1 semantics from:
- `src/spec_orch/domain/execution_semantics.py`

Do not duplicate type definitions unless the Phase 1 file cannot support re-export cleanly.

**Step 3: Add path helper stubs**

Define canonical normalized locations for:

- issue run normalized payloads
- mission worker normalized payloads
- mission round normalized payloads

**Step 4: Run tests**

```bash
pytest tests/unit/test_runtime_core_imports.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/runtime_core tests/unit/test_runtime_core_imports.py
git commit -m "feat: add runtime core package skeleton"
```

## Task 2: Move Normalized Read Logic Behind Runtime-Core

**Files:**
- Modify: `src/spec_orch/services/execution_semantics_reader.py`
- Create or Modify: `src/spec_orch/runtime_core/readers.py`
- Modify: `src/spec_orch/runtime_core/adapters.py`
- Test: `tests/unit/test_execution_semantics_reader.py`
- Test: `tests/unit/test_runtime_core_readers.py`

**Step 1: Write failing runtime-core reader tests**

Cover:
- issue workspace normalization
- mission worker normalization
- mission round normalization

Run:

```bash
pytest tests/unit/test_runtime_core_readers.py -v
```

**Step 2: Move or wrap existing readers**

Preferred direction:
- `services/execution_semantics_reader.py` becomes a compatibility shim
- `runtime_core/readers.py` becomes the real implementation

Do not leave two independent reader implementations in the tree.

**Step 3: Introduce adapter functions**

Examples:
- `load_issue_attempt(workspace)`
- `load_worker_attempt(worker_dir, mission_id, packet_id)`
- `load_round_cycle(round_dir)`

**Step 4: Run reader suites**

```bash
pytest tests/unit/test_execution_semantics_reader.py tests/unit/test_runtime_core_readers.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/runtime_core/readers.py src/spec_orch/runtime_core/adapters.py src/spec_orch/services/execution_semantics_reader.py tests/unit/test_execution_semantics_reader.py tests/unit/test_runtime_core_readers.py
git commit -m "refactor: route normalized reads through runtime core"
```

## Task 3: Move Normalized Write Logic Behind Runtime-Core

**Files:**
- Modify: `src/spec_orch/services/execution_semantics_writer.py`
- Modify: `src/spec_orch/runtime_core/writers.py`
- Modify: `src/spec_orch/runtime_core/paths.py`
- Test: `tests/unit/test_execution_semantics_writer.py`
- Test: `tests/unit/test_runtime_core_writers.py`

**Step 1: Write failing writer facade tests**

Cover:
- issue normalized write via runtime-core only
- mission worker normalized write via runtime-core only
- mission round normalized write via runtime-core only

Run:

```bash
pytest tests/unit/test_runtime_core_writers.py -v
```

**Step 2: Turn `execution_semantics_writer.py` into compatibility shim**

Preferred direction:
- owner-facing code imports runtime-core writer adapters
- old service module may remain temporarily as bridge, but not as independent implementation

**Step 3: Centralize normalized path decisions**

All normalized target paths must come from `runtime_core.paths`, not owner-local path concatenation.

**Step 4: Run writer suites**

```bash
pytest tests/unit/test_execution_semantics_writer.py tests/unit/test_runtime_core_writers.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/runtime_core/writers.py src/spec_orch/runtime_core/paths.py src/spec_orch/services/execution_semantics_writer.py tests/unit/test_execution_semantics_writer.py tests/unit/test_runtime_core_writers.py
git commit -m "refactor: route normalized writes through runtime core"
```

## Task 4: Make Issue Owner Delegate To Runtime-Core

**Files:**
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/services/run_report_writer.py`
- Modify: `src/spec_orch/services/run_artifact_service.py`
- Test: `tests/unit/test_run_controller.py`
- Test: `tests/unit/test_run_artifact_service.py`

**Step 1: Write failing delegation tests**

Cover:
- `RunController` no longer constructs normalized payload dicts itself
- normalized issue writes occur via runtime-core writer adapter

Run:

```bash
pytest tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py -v
```

**Step 2: Replace owner-local normalized JSON assembly**

Move normalized write orchestration behind a single call boundary, for example:

```python
runtime_core.adapters.write_issue_attempt(...)
```

`RunController` should still decide *when* to finalize, but not *how normalized payloads are laid out*.

**Step 3: Run tests**

```bash
pytest tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/run_controller.py src/spec_orch/services/run_report_writer.py src/spec_orch/services/run_artifact_service.py tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py
git commit -m "refactor: delegate issue normalized writes to runtime core"
```

## Task 5: Make Mission Leaf Owners Delegate To Runtime-Core

**Files:**
- Modify: `src/spec_orch/services/workers/oneshot_worker_handle.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Modify: `src/spec_orch/services/packet_executor.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_mission_execution_service.py`

**Step 1: Write failing delegation tests**

Cover:
- worker handles delegate normalized writes to runtime-core
- packet executors delegate normalized writes to runtime-core

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py -v
```

**Step 2: Replace owner-local normalized file decisions**

Mission leaf owners may still decide:
- attempt timing
- continuity kind
- owner kind

But they should not decide:
- normalized directory layout
- normalized JSON file names
- artifact-ref file structure

Those go through runtime-core.

**Step 3: Run tests**

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/workers/oneshot_worker_handle.py src/spec_orch/services/workers/acpx_worker_handle.py src/spec_orch/services/packet_executor.py src/spec_orch/services/round_orchestrator.py tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py
git commit -m "refactor: delegate mission leaf normalized writes to runtime core"
```

## Task 6: Make Round Supervision Delegate To Runtime-Core

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Modify: `src/spec_orch/runtime_core/supervision.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_dashboard.py`

**Step 1: Write failing supervision delegation tests**

Cover:
- round normalized supervision payloads are written via runtime-core
- `RoundOrchestrator` does not define normalized file structure inline

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py -v
```

**Step 2: Introduce supervision helpers**

`runtime_core/supervision.py` should own normalized round payload shaping, for example:

- supervision-cycle serialization
- round-level artifact-ref shaping
- linking packet attempts to supervision cycle

**Step 3: Run tests**

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/runtime_core/supervision.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/litellm_supervisor_adapter.py tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py
git commit -m "refactor: delegate supervision payloads to runtime core"
```

## Task 7: Migrate Consumers To Runtime-Core Facades Only

**Files:**
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/transcript.py`
- Modify: `src/spec_orch/dashboard/surfaces.py`
- Modify: `src/spec_orch/services/evidence_analyzer.py`
- Modify: `src/spec_orch/services/eval_runner.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Test: `tests/unit/test_dashboard.py`
- Test: `tests/unit/test_dashboard_api.py`
- Test: `tests/unit/test_evidence_analyzer.py`
- Test: `tests/unit/test_eval_runner.py`
- Test: `tests/unit/test_context_assembler.py`

**Step 1: Add failing tests that ban direct file-layout assumptions**

Add tests for cases where:
- normalized files exist
- legacy bridges still exist
- consumer behavior must remain stable

**Step 2: Replace raw file reads with runtime-core adapter calls**

Examples:
- `context_assembler` should not inspect manifest candidates directly
- dashboard mission views should not re-encode round file rules inline
- analytics should not hand-merge `conclusion.json` and `live.json` themselves

**Step 3: Run consumer suites**

```bash
pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_context_assembler.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/dashboard/control.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/transcript.py src/spec_orch/dashboard/surfaces.py src/spec_orch/services/evidence_analyzer.py src/spec_orch/services/eval_runner.py src/spec_orch/services/context/context_assembler.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_context_assembler.py
git commit -m "refactor: make consumers depend on runtime core facades"
```

## Task 8: Add Structural Guard Tests

**Files:**
- Create: `tests/unit/test_runtime_core_boundaries.py`
- Modify: existing suites as needed

**Step 1: Write guard tests for structural invariants**

Guard these rules:

- `RunController` does not construct normalized file paths inline
- `RoundOrchestrator` does not construct normalized supervision file paths inline
- dashboard readers do not hard-code normalized + legacy fallbacks themselves
- runtime-core is the only layer that shapes normalized `ArtifactRef` payloads

Run:

```bash
pytest tests/unit/test_runtime_core_boundaries.py -v
```

**Step 2: Make tests pass**

Use import boundaries, helper extraction, or monkeypatch expectations as appropriate.

**Step 3: Commit**

```bash
git add tests/unit/test_runtime_core_boundaries.py
git commit -m "test: guard runtime core structural boundaries"
```

## Task 9: Canonical Package Boundary Review

**Files:**
- Modify: `docs/architecture/shared-execution-semantics.md`
- Modify: `docs/plans/2026-03-29-shared-execution-semantics-rollout.md`
- Modify: `docs/architecture/object-boundaries.md`
- Optional: update README if operator-visible behavior changes

**Step 1: Update docs to reflect actual extracted package**

Once runtime-core exists in code, update docs so the program organization becomes visible in architecture materials.

**Step 2: Run final focused suite**

```bash
pytest tests/unit/test_runtime_core_imports.py tests/unit/test_runtime_core_readers.py tests/unit/test_runtime_core_writers.py tests/unit/test_runtime_core_boundaries.py tests/unit/test_run_controller.py tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py -v
```

**Step 3: Commit**

```bash
git add docs/architecture/shared-execution-semantics.md docs/plans/2026-03-29-shared-execution-semantics-rollout.md docs/architecture/object-boundaries.md README.md
git commit -m "docs: reflect runtime extraction phase 2 architecture"
```

## Risks

- Creating a runtime-core package that is just a pass-through alias layer
- Letting owner-specific fields leak back into the shared semantic models
- Preserving old writers and new writers side-by-side for too long
- Moving code without removing old raw readers, leaving two effective cores
- Accidentally using runtime-core as justification to merge closure locations

## Stop Conditions

Stop and reassess if:

- runtime-core cannot model both issue and mission without owner-specific hacks
- `Round` starts getting treated as an `ExecutionAttempt`
- normalized facades become thinner than direct file reads and no longer justify their existence
- read/write logic ends up duplicated in both runtime-core and owners

## Immediate Start Recommendation

If Phase 2 starts immediately after Phase 1, execute in this order:

1. Task 1: package skeleton
2. Task 2: reader extraction
3. Task 3: writer extraction
4. Task 4-6: owner delegation
5. Task 7-8: consumer migration + boundary guards
6. Task 9: docs and review

This keeps the refactor structural, not cosmetic.
