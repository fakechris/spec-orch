# Epic 1 Validation and PR Cut

**Date:** 2026-03-30  
**Scope:** `Epic 1: Shared Execution Semantics`  
**Purpose:** Record the implementation evidence, validation commands, bridge-retention policy, and PR cut recommendation for the shared execution semantics rollout.

## 1. Decision

`Epic 1` is complete enough to cut a PR.

This statement is based on code, tests, and the current package shape, not on a future-plan interpretation. The repo now has:

- shared execution semantic models
- normalized issue / mission leaf / mission round readers
- normalized readers adopted by dashboard, analytics, and context consumers
- normalized write helpers and live owner delegation on issue and mission paths
- canonical normalized carriers with explicit compatibility bridges still present where needed

This means the rollout has passed the point of being a semantic experiment. It is now a real system seam and a valid PR boundary.

## 2. Epic 1 Issue Status

### E1-I1 `Add shared execution semantic models`

Status: complete

Evidence:

- [`src/spec_orch/domain/execution_semantics.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/domain/execution_semantics.py)
- [`tests/unit/test_execution_semantics.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_execution_semantics.py)

### E1-I2 `Add read-side normalizers for issue and mission artifacts`

Status: complete

Evidence:

- [`src/spec_orch/runtime_core/readers.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/runtime_core/readers.py)
- [`src/spec_orch/services/execution_semantics_reader.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/execution_semantics_reader.py)
- [`tests/unit/test_execution_semantics_reader.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_execution_semantics_reader.py)
- [`tests/unit/test_runtime_core_readers.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_runtime_core_readers.py)

### E1-I3 `Migrate read-side consumers to normalized execution reads`

Status: complete

Evidence:

- [`src/spec_orch/services/evidence_analyzer.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/evidence_analyzer.py)
- [`src/spec_orch/services/eval_runner.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/eval_runner.py)
- [`src/spec_orch/services/context/context_assembler.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/context/context_assembler.py)
- [`src/spec_orch/dashboard/control.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/dashboard/control.py)
- [`src/spec_orch/dashboard/missions.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/dashboard/missions.py)
- [`src/spec_orch/dashboard/transcript.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/dashboard/transcript.py)
- [`src/spec_orch/dashboard/surfaces.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/dashboard/surfaces.py)

### E1-I4 `Add issue-path dual-write for normalized execution payloads`

Status: complete

Evidence:

- [`src/spec_orch/runtime_core/writers.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/runtime_core/writers.py)
- [`src/spec_orch/services/run_artifact_service.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/run_artifact_service.py)
- [`src/spec_orch/services/run_report_writer.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/run_report_writer.py)
- [`tests/unit/test_run_artifact_service.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_run_artifact_service.py)
- [`tests/unit/test_run_report_writer.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_run_report_writer.py)

### E1-I5 `Add mission leaf dual-write for normalized execution payloads`

Status: complete for current leaf owners

Evidence:

- [`src/spec_orch/services/workers/acpx_worker_handle.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/workers/acpx_worker_handle.py)
- [`tests/unit/test_acpx_worker_handle.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_acpx_worker_handle.py)

Note:

`OneShotWorkerHandle` was intentionally not expanded because it does not directly own the normalized builder-report write path. This does not block Epic 1 completion because the canonical mission leaf write seam now exists and is already consumed by a real mission leaf owner.

### E1-I6 `Add mission round dual-write for normalized supervision payloads`

Status: complete

Evidence:

- [`src/spec_orch/services/round_orchestrator.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/services/round_orchestrator.py)
- [`tests/unit/test_round_orchestrator.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/tests/unit/test_round_orchestrator.py)

### E1-I7 `Cut readers over to normalized execution preference`

Status: complete

Evidence:

- reader shim now points at [`src/spec_orch/runtime_core/readers.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/runtime_core/readers.py)
- dashboard / analytics / context consumers prefer normalized reads and retain fallback behavior

### E1-I8 `Cut canonical writes over to normalized execution payloads with bridge retention`

Status: complete

Evidence:

- writer shim now points at [`src/spec_orch/runtime_core/writers.py`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/src/spec_orch/runtime_core/writers.py)
- canonical write helpers live in runtime-core
- bridge metadata remains explicit in legacy compatibility outputs

Bridge retention in current state:

- issue-path legacy `report.json` is still preserved
- issue-path `artifact_manifest.json` is still preserved as a compatibility bridge
- normalized readers prefer canonical `run_artifact/manifest.json` and fall back to legacy bridge files when needed

### E1-I9 `Validate shared execution semantics rollout and stop conditions`

Status: complete

This document is the explicit validation checkpoint for `Epic 1`.

## 3. Bridge Retention Policy

The current policy is:

- canonical normalized carriers are now the preferred write/read path
- legacy bridges remain only where downstream compatibility still exists
- bridges are not a license to keep adding new semantics to legacy files

Current retained bridges:

- `report.json`
- `artifact_manifest.json`

Current canonical normalized carriers:

- `run_artifact/live.json`
- `run_artifact/conclusion.json`
- `run_artifact/manifest.json`
- mission `builder_report.json`
- mission `round_summary.json`
- mission `round_decision.json`

## 4. Stop Conditions Review

### Stop Condition 1

`Round` must remain a `SupervisionCycle`, not collapse into `ExecutionAttempt`.

Status: satisfied

Evidence:

- normalized round reading stays in supervision-shaped structures
- round writers remain in round-specific helpers
- tests explicitly cover embedded decision fallback without retyping round as attempt

### Stop Condition 2

Read preference must move to normalized carriers without breaking legacy fallback.

Status: satisfied

Evidence:

- issue-path normalized readers still fall back to `report.json` and `artifact_manifest.json`
- dashboard approval/history readers now prefer decision-core response/intervention carriers while retaining old action history fallback

### Stop Condition 3

Normalized write path must be real, not only documentary.

Status: satisfied

Evidence:

- issue owner delegates writes through runtime-core
- mission leaf owner delegates writes through runtime-core
- mission round owner delegates writes through runtime-core

### Stop Condition 4

Shared semantics must have at least one real consumer in every major read category.

Status: satisfied

Evidence:

- dashboard consumers
- analytics/eval consumers
- context assembly consumer

## 5. Verification Commands

These focused commands provide sufficient evidence for the Epic 1 PR cut:

```bash
uv run --python 3.13 python -m pytest \
  tests/unit/test_execution_semantics.py \
  tests/unit/test_execution_semantics_reader.py \
  tests/unit/test_runtime_core_readers.py \
  tests/unit/test_runtime_core_writers.py \
  tests/unit/test_run_artifact_service.py \
  tests/unit/test_run_report_writer.py \
  tests/unit/test_acpx_worker_handle.py \
  tests/unit/test_round_orchestrator.py \
  tests/unit/test_evidence_analyzer.py \
  tests/unit/test_eval_runner.py \
  tests/unit/test_context_assembler.py \
  tests/unit/test_dashboard_api.py \
  tests/unit/test_dashboard_missions.py \
  tests/unit/test_dashboard_approvals.py -v
```

## 6. PR Cut Recommendation

Cut the first PR here.

Recommended PR scope:

- all `Epic 1` implementation
- the already-landed `runtime_core` package extraction needed to support that implementation
- no attempt to include the full later-epic story in the PR narrative

Recommended exclusions from the PR:

- [`findings.md`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/findings.md)
- [`progress.md`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/progress.md)
- [`task_plan.md`](/Users/chris/.superset/worktrees/spec-orch/llm_planner_orch/task_plan.md)

## 7. Next Start Point After PR

After this PR lands, the next implementation entry point should be `Epic 3 / E3-I5` or the next explicitly chosen `decision_core` expansion batch, not a reopening of `Epic 1`.
