# First-Week Implementation Tranches

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the agreed shared-semantics + runtime-core + decision-core direction into 6 executable task groups that can start immediately without reopening architectural debate.

**Architecture:** The first week should not attempt full system reorganization. It should establish the minimum visible seams that stop new abstractions from landing in `services/` ad hoc: `runtime_core` as the normalized execution seam and `decision_core` as the normalized supervision/intervention seam. Existing owners remain in place and delegate into the new seams through compatibility shims.

**Tech Stack:** Python 3.13, dataclasses, JSON/JSONL/Markdown carriers, existing `src/spec_orch` tree, pytest.

---

## Scope Boundary

This plan is intentionally narrower than the full implementation track.

It only covers the first week of structural work:

- package skeletons
- runtime-core seam
- decision-core primitives
- first mission-path integration
- no broad UI rewrite
- no memory/evolution refactor
- no contract-core extraction

## Important Note

This plan is still **implementation planning**, not the final work-management breakdown.

Before coding starts, this work must still be mapped into:

- Linear Epic(s)
- Linear Issues
- explicit sequencing / ownership / acceptance criteria per issue

That Linearization step is required before execution.

---

## Tranche 1: Package Skeletons and Import Boundaries

**Objective:** Create visible homes for extracted primitives before moving behavior.

**Files:**
- Create: `src/spec_orch/runtime_core/__init__.py`
- Create: `src/spec_orch/runtime_core/models.py`
- Create: `src/spec_orch/runtime_core/paths.py`
- Create: `src/spec_orch/runtime_core/readers.py`
- Create: `src/spec_orch/runtime_core/writers.py`
- Create: `src/spec_orch/runtime_core/adapters.py`
- Create: `src/spec_orch/decision_core/__init__.py`
- Create: `src/spec_orch/decision_core/models.py`
- Create: `src/spec_orch/decision_core/records.py`
- Create: `src/spec_orch/decision_core/interventions.py`
- Create: `src/spec_orch/decision_core/review_queue.py`
- Test: `tests/unit/test_runtime_core_imports.py`
- Test: `tests/unit/test_decision_core_imports.py`

**Outcomes:**
- New shared primitives stop defaulting into `services/`
- Import tests define the canonical home for new runtime and decision abstractions

**Verification:**

```bash
pytest tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py -v
```

**Commit boundary:**
- one commit for package skeletons only

---

## Tranche 2: Runtime-Core Models and Path Rules

**Objective:** Land the minimal execution semantic types and canonical normalized path helpers.

**Files:**
- Modify: `src/spec_orch/runtime_core/models.py`
- Modify: `src/spec_orch/runtime_core/paths.py`
- Test: `tests/unit/test_execution_semantics.py`
- Create or Modify: `tests/unit/test_runtime_core_paths.py`

**Include:**
- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- continuity enums / helpers
- canonical normalized target path helpers

**Do not include yet:**
- owner orchestration logic
- dashboard semantics
- memory linkage

**Verification:**

```bash
pytest tests/unit/test_execution_semantics.py tests/unit/test_runtime_core_paths.py -v
```

**Commit boundary:**
- one commit for models + paths only

---

## Tranche 3: Runtime-Core Reader/Writer Seam

**Objective:** Make normalized execution semantics real through runtime-core readers and writers.

**Files:**
- Modify: `src/spec_orch/runtime_core/readers.py`
- Modify: `src/spec_orch/runtime_core/writers.py`
- Modify: `src/spec_orch/runtime_core/adapters.py`
- Create: `src/spec_orch/services/execution_semantics_reader.py`
- Create: `src/spec_orch/services/execution_semantics_writer.py`
- Test: `tests/unit/test_execution_semantics_reader.py`
- Test: `tests/unit/test_execution_semantics_writer.py`
- Create or Modify: `tests/unit/test_runtime_core_readers.py`
- Create or Modify: `tests/unit/test_runtime_core_writers.py`

**Behavioral target:**
- issue leaf normalization supported
- mission worker normalization supported
- mission round normalization supported

**Compatibility target:**
- old service-level entrypoints become shims
- real implementation lives in `runtime_core`

**Verification:**

```bash
pytest tests/unit/test_execution_semantics_reader.py tests/unit/test_execution_semantics_writer.py tests/unit/test_runtime_core_readers.py tests/unit/test_runtime_core_writers.py -v
```

**Commit boundary:**
- one commit for read seam
- one commit for write seam

---

## Tranche 4: Owner Delegation Into Runtime-Core

**Objective:** Make existing owners consume the runtime-core seam instead of hand-rolling normalized payloads.

**Files:**
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/services/run_report_writer.py`
- Modify: `src/spec_orch/services/run_artifact_service.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/packet_executor.py`
- Modify: `src/spec_orch/services/workers/oneshot_worker_handle.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Test: `tests/unit/test_run_controller.py`
- Test: `tests/unit/test_run_artifact_service.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_mission_execution_service.py`

**Rule:**
- owners still decide *when* to execute / finalize / retry / continue
- owners no longer decide *how normalized execution payloads are shaped*

**Verification:**

```bash
pytest tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py -v
```

**Commit boundary:**
- one commit for issue-owner delegation
- one commit for mission-owner delegation

---

## Tranche 5: Decision-Core Primitives and Inventory

**Objective:** Create the first-class decision vocabulary that the current repo lacks.

**Files:**
- Modify: `src/spec_orch/decision_core/models.py`
- Modify: `src/spec_orch/decision_core/records.py`
- Modify: `docs/architecture/evolution-trigger-architecture.md`
- Modify: `docs/architecture/runtime-glossary.md`
- Test: `tests/unit/test_decision_core_models.py`
- Test: `tests/unit/test_decision_core_records.py`

**Include:**
- `DecisionPoint`
- `DecisionRecord`
- `Intervention`
- inventory categories:
  - rule-owned
  - LLM-owned
  - human-required

**Do not include yet:**
- full decision-quality scoring system
- memory/evolution promotion linkage

**Verification:**

```bash
pytest tests/unit/test_decision_core_models.py tests/unit/test_decision_core_records.py -v
```

**Commit boundary:**
- one commit for primitives
- one commit for decision-point inventory docs

---

## Tranche 6: Mission Supervision Integration

**Objective:** Make Mission the first real adopter of decision-core.

**Files:**
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/dashboard/approvals.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/decision_core/records.py`
- Modify: `src/spec_orch/decision_core/interventions.py`
- Modify: `src/spec_orch/decision_core/review_queue.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_dashboard.py`
- Test: `tests/unit/test_dashboard_api.py`
- Test: `tests/unit/test_decision_core_records.py`

**Behavioral target:**
- round review emits `DecisionRecord`
- `ask_human` emits explicit `Intervention`
- approval queue consumes decision-core state rather than inferring it ad hoc from dashboard helpers

**Verification:**

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_decision_core_records.py -v
```

**Commit boundary:**
- one commit for supervisor adapter + round writes
- one commit for dashboard approval consumption

---

## Recommended Order

Run these task groups in this exact order:

1. Tranche 1: Package Skeletons and Import Boundaries
2. Tranche 2: Runtime-Core Models and Path Rules
3. Tranche 3: Runtime-Core Reader/Writer Seam
4. Tranche 4: Owner Delegation Into Runtime-Core
5. Tranche 5: Decision-Core Primitives and Inventory
6. Tranche 6: Mission Supervision Integration

This order matters because:

- Tranche 1-4 establish the execution seam
- Tranche 5-6 establish the decision seam on top of that execution seam

## Explicit Deferrals

Not in the first-week tranche:

- `services/memory/*` structural changes
- `services/evolution/*` structural changes
- `contract_core/` extraction
- wide dashboard UI redesign
- daemon orchestration rewrite
- flow-router / reaction-engine / skill-degradation unification
- full Linear issue management integration

## Linearization Requirement Before Start

Before implementation begins, convert these tranches into work items.

Minimum required management structure:

- `Epic A`: Runtime Core Extraction
  - Tranche 1
  - Tranche 2
  - Tranche 3
  - issue-owner half of Tranche 4
  - mission-owner half of Tranche 4

- `Epic B`: Decision Core Extraction
  - Tranche 5
  - Tranche 6

Each resulting Linear issue should include:

- exact file list
- acceptance criteria
- test command
- dual-write / shim constraint if applicable
- explicit non-goals

That Linear mapping is still pending and must be completed before coding starts.
