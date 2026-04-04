# Findings

## 2026-04-04

### Baseline

- Local `main` and `origin/main` both resolve to `4e7c0abda1a1afc33d28a66f8f46f7617b5d9648`.
- New worktree: `/Users/chris/workspace/spec-orch/.worktrees/self-hosting-dogfood-start`
- Focused self-hosting baseline is green:
  - `tests/unit/test_linear_mirror.py`
  - `tests/unit/test_conversation_service.py`
  - `tests/unit/test_dashboard_launcher.py`
  - `tests/unit/test_daemon.py`
  - `tests/unit/test_linear_conversation.py`
  - result: `67 passed`

### Existing Landed Capability

- `linear_mirror.py` already owns the structured `## SpecOrch Mirror` block.
- `linear_plan_sync.py` already projects compact plan state into the mirror.
- `ConversationService.freeze` already persists intake workspace and can sync a linked Linear issue.
- `spec-orch linear-sync` already exists as a backfill entrypoint.

### Current Gap

- The current sync seam is mutation-first; it needs a report/inventory pass before bulk correction.
- Plan mirroring is present but still mission-local and compact; it does not yet expose tranche-level bottleneck/review state strongly enough for dogfood governance.
- The `chat-to-issue` path exists, but it still needs to be treated as a first-class lifecycle with explicit acceptance closeout.

### Task 1 Outcome

- Added report-first drift inventory instead of mutation-only `linear-sync`.
- New drift classifications now exist:
  - `missing_mirror`
  - `stale_plan_sync`
  - `workspace_mismatch`
  - `already_synced`
- `LinearWriteBackService` now has a preview seam so callers can inspect drift without mutating Linear.

### Task 2 Outcome

- The mirror now carries a separate `governance_sync` projection.
- The first compact governance fields are:
  - `latest_acceptance_status`
  - `latest_release_id`
  - `latest_release_bundle_path`
  - `next_bottleneck`
- These sources stay intentionally compact:
  - acceptance summary from `.spec_orch/acceptance/stability_acceptance_status.json`
  - latest archived release from `docs/acceptance-history/index.json`
  - mission-local bottleneck from `launch.json` metadata

### Task 3 Outcome

- `ConversationService.freeze` now has an explicit idempotent response for already-frozen threads.
- `launch.json` now keeps `conversation_thread` provenance:
  - `thread_id`
  - `channel`
  - `status`
  - `linear_issue_id`
  - `linear_identifier`
- This makes the `chat -> freeze -> workspace -> Linear` path easier to audit as a lifecycle, instead of leaving thread origin implicit.

### Closeout Review

- Canonical acceptance returned `overall_status=pass`.
- New archive bundle:
  - `docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04`
- `5-subsystem` review result:
  - `Instructions`: pass
  - `State`: pass
  - `Verification`: pass
  - `Scope`: pass
  - `Lifecycle`: weakest-pass
- Next bottleneck stays `Lifecycle`, because the system now has the right capabilities but still needs more routine self-hosting evidence and operator repetition.

### Post-Closeout Hygiene Finding

- The first green closeout still leaked absolute local paths in fresh `docs/specs/*` source runs.
- Root cause was broader than `stability_acceptance.py`:
  - `operator/observability/*`
  - `operator/runtime_chain/*`
  - `rounds/*/builder_execution_summary.json`
  - worker telemetry files such as `incoming_events.jsonl`
- The pragmatic fix is a mission-tree text artifact sanitizer:
  - implemented in `src/spec_orch/services/path_sanitizer.py`
  - wired into `tests/e2e/fresh_acpx_mission_smoke.sh`
  - wired into `tests/e2e/exploratory_acceptance_smoke.sh`
- This keeps binary evidence untouched while removing local absolute paths from the tracked source-run tree before archive closeout.

### Research Inputs To Absorb

- `5-subsystem` tranche review:
  - `Instructions`
  - `State`
  - `Verification`
  - `Scope`
  - `Lifecycle`
- `bottleneck-first` rule: fix the weakest subsystem next instead of broadening scope.
- Context taxonomy:
  - `Active Context`
  - `Working State`
  - `Review Evidence`
  - `Archive`
  - `Promoted Learning`
- Acceptance hardening protocol now available on `main`:
  - exploratory `functional / adversarial / coverage_gaps / merged_plan`
  - browser `STEP_PASS / STEP_FAIL / STEP_SKIP`
  - fixed failure artifact fields
