# Shared Execution Semantics Rollout Implementation Plan

> **Status 2026-03-30:** The implementation slice described here has been materially completed. Validation and PR cut guidance now live in [`2026-03-30-epic-1-validation-and-pr-cut.md`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/docs/plans/2026-03-30-epic-1-validation-and-pr-cut.md).

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a shared semantic layer for `ExecutionUnit`, `ExecutionAttempt`, `ExecutionOutcome`, `ArtifactRef`, and `SupervisionCycle`, then roll it out through read-side convergence, dual-write, and canonical write cutover without forcing a single runtime owner.

**Architecture:** Add a small domain-level semantic model first, then build read adapters that can normalize current issue and mission artifacts into that model. Once the normalized read model is stable in dashboard/analytics/context consumers, add dual-write emitters to issue leaf, mission leaf, and mission round paths. Only after both read and write paths are stable should the codebase start treating the shared semantic payloads as canonical.

**Tech Stack:** Python 3.13, dataclasses, existing `domain/models.py` conventions, Typer/FastAPI dashboard readers, JSON/JSONL artifact files, pytest unit tests.

## Principles

- Keep owners separate: do not merge `RunController`, `RoundOrchestrator`, or `MissionLifecycleManager`.
- Share semantics before ownership: normalize what the system means first, not how the system is implemented.
- Dual-write before cutover: never switch canonical readers and writers in one step.
- Preserve legacy artifacts until all read paths have migrated.
- Keep `Round` as a `SupervisionCycle`, not as an `ExecutionAttempt`.

## Target Deliverables

1. A domain-level semantic model for:
   - `ExecutionUnitRef`
   - `ExecutionAttempt`
   - `ExecutionOutcome`
   - `ArtifactRef`
   - `SupervisionCycleRef`
2. Read adapters that can normalize:
   - issue run artifacts
   - mission leaf worker artifacts
   - mission round artifacts
3. Dual-write emitters that write normalized payloads alongside legacy artifacts.
4. Dashboard, analytics, and context readers migrated to normalized read-side.
5. Canonical write cutover plan with compatibility bridges retained temporarily.

## Task 1: Add Shared Semantic Domain Models

**Files:**
- Create: `src/spec_orch/domain/execution_semantics.py`
- Modify: `src/spec_orch/domain/__init__.py` if exports exist
- Test: `tests/unit/test_execution_semantics.py`

**Step 1: Write the failing tests for semantic dataclasses**

Add tests for:
- `ExecutionOutcome.status` accepts only `succeeded`, `failed`, `partial`, `blocked`
- `ExecutionAttempt.attempt_state` accepts only `created`, `running`, `completed`, `cancelled`
- `ArtifactRef.scope` accepts only `leaf`, `round`
- nullable `review`, `gate`, `continuity_id`

Run:

```bash
pytest tests/unit/test_execution_semantics.py -v
```

Expected: missing module / missing classes.

**Step 2: Implement minimal semantic dataclasses**

Create:
- enums for `UnitKind`, `OwnerKind`, `OutcomeStatus`, `AttemptState`, `ArtifactScope`, `CarrierKind`, `ContinuityKind`
- dataclasses for `ArtifactRef`, `ExecutionOutcome`, `ExecutionAttempt`
- JSON helpers `to_dict()` / `from_dict()` matching existing repo style

Do not import runtime owners here.

**Step 3: Run semantic model tests**

Run:

```bash
pytest tests/unit/test_execution_semantics.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add src/spec_orch/domain/execution_semantics.py tests/unit/test_execution_semantics.py
git commit -m "feat: add shared execution semantics domain model"
```

## Task 2: Add Read-Side Normalizers

**Files:**
- Create: `src/spec_orch/services/execution_semantics_reader.py`
- Test: `tests/unit/test_execution_semantics_reader.py`
- Reference: `src/spec_orch/services/run_report_writer.py`
- Reference: `src/spec_orch/services/run_artifact_service.py`
- Reference: `src/spec_orch/services/round_orchestrator.py`

**Step 1: Write failing tests for three normalization paths**

Cover:
- issue workspace -> `ExecutionAttempt`
- mission worker workspace -> `ExecutionAttempt`
- mission round directory -> `SupervisionCycleRef` plus `ArtifactRef`s

Use small fixture directories under `tmp_path` rather than full repo fixtures.

Run:

```bash
pytest tests/unit/test_execution_semantics_reader.py -v
```

Expected: FAIL with missing reader functions.

**Step 2: Implement issue-path reader**

Add functions similar to:
- `read_issue_execution_attempt(workspace: Path) -> ExecutionAttempt | None`
- `read_issue_artifacts(workspace: Path) -> dict[str, ArtifactRef]`

Read from:
- `run_artifact/live.json`
- `report.json`
- `run_artifact/manifest.json`
- `artifact_manifest.json`
- `review_report.json`
- `explain.md`
- `acceptance.json`

The reader must treat normalized semantics as an interpretation layer, not require new files yet.

**Step 3: Implement mission leaf reader**

Add:
- `read_worker_execution_attempt(worker_dir: Path, *, mission_id: str, packet_id: str) -> ExecutionAttempt | None`

Read from:
- `builder_report.json`
- `telemetry/incoming_events.jsonl`
- `telemetry/activity.log`

Set:
- `unit_kind = work_packet`
- `owner_kind = round_worker`
- `continuity_kind = worker_session` or `oneshot_worker` based on evidence available

**Step 4: Implement mission round reader**

Add:
- `read_round_supervision_cycle(round_dir: Path) -> dict[str, Any]`

Normalize:
- `round_summary.json`
- `round_decision.json`
- `supervisor_review.md`
- `visual_evaluation.json`
- `acceptance_review.json`

Do not pretend this is an `ExecutionAttempt`.

**Step 5: Run reader tests**

Run:

```bash
pytest tests/unit/test_execution_semantics_reader.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/spec_orch/services/execution_semantics_reader.py tests/unit/test_execution_semantics_reader.py
git commit -m "feat: add execution semantics read adapters"
```

## Task 3: Migrate Read-Side Consumers

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

**Step 1: Migrate analytics readers first**

Update:
- `evidence_analyzer.py`
- `eval_runner.py`

They should prefer normalized read adapters, then fall back to legacy raw files.

Run:

```bash
pytest tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py -v
```

Expected: existing tests pass; add new tests for normalized preference.

**Step 2: Migrate context assembly manifest loading**

Update `context_assembler.py` so it can consume normalized artifact refs before raw manifest fallback.

Run:

```bash
pytest tests/unit/test_context_assembler.py -v
```

**Step 3: Migrate dashboard issue views**

Update `dashboard/control.py` to build its issue summaries from normalized issue attempts/outcomes when present.

**Step 4: Migrate dashboard mission views**

Update:
- `dashboard/missions.py`
- `dashboard/transcript.py`
- `dashboard/surfaces.py`

Use normalized round/worker readers so UI logic stops depending on ad hoc file-name branching.

Run:

```bash
pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/control.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/transcript.py src/spec_orch/dashboard/surfaces.py src/spec_orch/services/evidence_analyzer.py src/spec_orch/services/eval_runner.py src/spec_orch/services/context/context_assembler.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_context_assembler.py
git commit -m "refactor: migrate readers to execution semantics layer"
```

## Task 4: Add Issue-Path Dual-Write

**Files:**
- Create: `src/spec_orch/services/execution_semantics_writer.py`
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/services/run_report_writer.py`
- Modify: `src/spec_orch/services/run_artifact_service.py`
- Test: `tests/unit/test_run_controller.py`
- Test: `tests/unit/test_run_artifact_service.py`
- Test: `tests/unit/test_execution_semantics_writer.py`

**Step 1: Write failing tests for issue dual-write**

Cover:
- after finalized issue run, normalized attempt/outcome files exist
- legacy files still exist unchanged
- normalized payload references the same workspace evidence

Run:

```bash
pytest tests/unit/test_execution_semantics_writer.py tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py -v
```

**Step 2: Implement normalized write helpers**

Add helpers like:
- `write_issue_execution_attempt(...)`
- `write_issue_execution_outcome(...)`
- `write_artifact_refs(...)`

Recommended target directory:

```text
<workspace>/run_artifact/normalized/
  execution_attempt.json
  execution_outcome.json
  artifact_refs.json
```

Do not replace existing `live.json` / `conclusion.json` yet.

**Step 3: Hook issue dual-write into finalization**

Wire dual-write after:
- `RunReportWriter.write_report(...)`
- `RunReportWriter.write_artifact_manifest(...)`
- `RunArtifactService.write_from_run(...)`

Prefer writing normalized payloads once all legacy artifacts are already on disk.

**Step 4: Run tests**

Run:

```bash
pytest tests/unit/test_execution_semantics_writer.py tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/services/execution_semantics_writer.py src/spec_orch/services/run_controller.py src/spec_orch/services/run_report_writer.py src/spec_orch/services/run_artifact_service.py tests/unit/test_execution_semantics_writer.py tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py
git commit -m "feat: dual-write normalized issue execution semantics"
```

## Task 5: Add Mission Leaf Dual-Write

**Files:**
- Modify: `src/spec_orch/services/workers/oneshot_worker_handle.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Modify: `src/spec_orch/services/packet_executor.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_mission_execution_service.py`
- Test: `tests/unit/test_execution_semantics_writer.py`

**Step 1: Write failing tests for mission leaf normalized writes**

Cover:
- worker execution writes normalized attempt/outcome for each packet workspace
- packet executor writes normalized attempt/outcome for each packet attempt
- no requirement yet for review/gate to be present at leaf level

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py tests/unit/test_execution_semantics_writer.py -v
```

**Step 2: Add worker-side normalized writes**

After `BuilderResult` is available in:
- `OneShotWorkerHandle.send()`
- `AcpxWorkerHandle.send()`

write:
- `execution_attempt.json`
- `execution_outcome.json`
- `artifact_refs.json`

under the packet workspace normalized directory.

**Step 3: Add packet-executor normalized writes**

For `SubprocessPacketExecutor` and `FullPipelinePacketExecutor`, emit the same normalized payloads, even if `review` and `gate` are null.

**Step 4: Run mission leaf tests**

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py tests/unit/test_execution_semantics_writer.py -v
```

**Step 5: Commit**

```bash
git add src/spec_orch/services/workers/oneshot_worker_handle.py src/spec_orch/services/workers/acpx_worker_handle.py src/spec_orch/services/packet_executor.py src/spec_orch/services/round_orchestrator.py tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py tests/unit/test_execution_semantics_writer.py
git commit -m "feat: dual-write normalized mission leaf execution semantics"
```

## Task 6: Add Mission Round Dual-Write

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_dashboard.py`

**Step 1: Write failing tests for round-level normalized outputs**

Cover:
- round writes normalized supervision payload
- round artifact refs include `review_report`, `visual_report`, `acceptance_report`, `browser_evidence` when present
- round output links the supervised packet attempt refs

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py -v
```

**Step 2: Add normalized round payloads**

Recommended target directory:

```text
docs/specs/<mission_id>/rounds/round-XX/normalized/
  supervision_cycle.json
  artifact_refs.json
```

This payload should reference:
- `round_summary.json`
- `round_decision.json`
- `supervisor_review.md`
- `visual_evaluation.json`
- `acceptance_review.json`

**Step 3: Run tests**

Run:

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/round_orchestrator.py src/spec_orch/services/litellm_supervisor_adapter.py tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py
git commit -m "feat: dual-write normalized mission round supervision semantics"
```

## Task 7: Make Normalized Writes Canonical For Readers

**Files:**
- Modify: `src/spec_orch/services/execution_semantics_reader.py`
- Modify: `src/spec_orch/services/evidence_analyzer.py`
- Modify: `src/spec_orch/services/eval_runner.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Modify: dashboard readers touched in Task 3
- Test: affected unit suites above

**Step 1: Flip reader preference order**

Change readers to prefer:

1. normalized semantic payloads
2. existing unified artifacts
3. legacy bridge artifacts

**Step 2: Add regression tests for fallback order**

Cover:
- normalized present -> use normalized
- normalized absent -> use unified legacy
- unified absent -> use oldest bridge

**Step 3: Run focused suites**

Run:

```bash
pytest tests/unit/test_execution_semantics_reader.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_context_assembler.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/execution_semantics_reader.py src/spec_orch/services/evidence_analyzer.py src/spec_orch/services/eval_runner.py src/spec_orch/services/context/context_assembler.py src/spec_orch/dashboard/control.py src/spec_orch/dashboard/missions.py src/spec_orch/dashboard/transcript.py src/spec_orch/dashboard/surfaces.py tests/unit/test_execution_semantics_reader.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_context_assembler.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py
git commit -m "refactor: prefer normalized execution semantics in readers"
```

## Task 8: Canonical Write Cutover and Bridge Retention

**Files:**
- Modify: `src/spec_orch/services/run_report_writer.py`
- Modify: `src/spec_orch/services/run_artifact_service.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/execution_semantics_writer.py`
- Modify: relevant docs in `docs/architecture/` and `README.md` if behavior changes are user-visible
- Test: full focused suites above

**Step 1: Define canonical semantic write targets**

Issue path canonical targets:

```text
run_artifact/normalized/execution_attempt.json
run_artifact/normalized/execution_outcome.json
run_artifact/normalized/artifact_refs.json
```

Mission round canonical targets:

```text
rounds/round-XX/normalized/supervision_cycle.json
rounds/round-XX/normalized/artifact_refs.json
```

Mission leaf canonical targets:

```text
workers/<packet_id>/normalized/execution_attempt.json
workers/<packet_id>/normalized/execution_outcome.json
workers/<packet_id>/normalized/artifact_refs.json
```

**Step 2: Keep legacy bridges during at least one release window**

Continue writing:
- `report.json`
- `run_artifact/live.json`
- `artifact_manifest.json`
- `round_summary.json`
- `round_decision.json`

until all consumers are proven migrated.

**Step 3: Run final focused suite**

Run:

```bash
pytest tests/unit/test_execution_semantics.py tests/unit/test_execution_semantics_reader.py tests/unit/test_execution_semantics_writer.py tests/unit/test_run_controller.py tests/unit/test_run_artifact_service.py tests/unit/test_round_orchestrator.py tests/unit/test_mission_execution_service.py tests/unit/test_context_assembler.py tests/unit/test_evidence_analyzer.py tests/unit/test_eval_runner.py tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/run_report_writer.py src/spec_orch/services/run_artifact_service.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/execution_semantics_writer.py docs/architecture/*.md README.md
git commit -m "refactor: cut over to normalized execution semantics writes"
```

## Task 9: Validation Matrix

**Files:**
- Modify: `tests/unit/test_run_controller.py`
- Modify: `tests/unit/test_round_orchestrator.py`
- Modify: `tests/unit/test_dashboard.py`
- Create: `tests/unit/test_execution_semantics_end_to_end.py`

**Step 1: Add validation matrix tests**

Cover these cases:

1. issue leaf full closure
2. mission leaf sparse closure
3. run-plan packet thin closure
4. mission round supervision closure
5. normalized read fallback to legacy
6. normalized write and legacy bridge both present

**Step 2: Run matrix**

Run:

```bash
pytest tests/unit/test_execution_semantics_end_to_end.py -v
```

**Step 3: Commit**

```bash
git add tests/unit/test_execution_semantics_end_to_end.py tests/unit/test_run_controller.py tests/unit/test_round_orchestrator.py tests/unit/test_dashboard.py
git commit -m "test: cover shared execution semantics rollout matrix"
```

## Risks To Watch

- Accidentally treating `Round` as an `ExecutionAttempt`
- Letting `status` duplicate `gate`
- Making `continuity_kind` a proxy for owner type
- Overwriting legacy readers before dual-write is stable
- Forcing mission leaf writers to invent fake `review` or `gate`
- Encoding filenames into semantic keys

## Stop Conditions

Stop and reassess if any of the following happens:

- a shared schema requires mission leaf to fake full issue closure
- dashboard readers become more coupled to file layout, not less
- the normalized model needs owner-specific fields to work
- `ExecutionAttempt` starts absorbing `RoundDecision` semantics

## Immediate Start Recommendation

If implementation begins now, start with:

1. Task 1: semantic domain models
2. Task 2: read-side normalizers
3. Task 3: analytics + dashboard read-side migration

That sequence gives the fastest proof that the semantic layer is real before write-side cutover begins.
