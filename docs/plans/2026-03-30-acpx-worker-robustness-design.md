# ACPX Worker Robustness Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ACPX-backed mission execution bounded, observable, and safe under repeated acceptance runs, with explicit completion, degradation, retry, and cleanup semantics.

**Architecture:** Replace the current "wait for subprocess exit" contract with a small worker-session state machine driven by progress signals from ACPX JSON events, bounded timers, and explicit terminal reasons. Keep ACPX session reuse, but bound it by turn count, age, and health. Treat prompt-envelope correctness as part of runtime robustness, not a separate prompt polish task.

**Tech Stack:** Python 3.13, existing `AcpxWorkerHandle`, `AcpxWorkerHandleFactory`, `round_orchestrator`, `fresh_acpx_e2e`, file-backed worker telemetry, pytest.

## 1. Problem Statement

The current mission worker path is too optimistic in two places:

1. `AcpxWorkerHandle.send()` treats **process exit** as the only reliable completion signal.
2. The worker prompt envelope can ask ACPX to **read files that do not exist yet**, especially for scaffold-style packets where `files_in_scope` is really an output set.

That combination is fragile during real E2E acceptance:

- some runs do useful work, emit verification events, then never produce a clean subprocess exit quickly enough
- some runs enter a bad branch immediately after a failed `read`
- stderr can show `agent needs reconnect`, but the caller has no explicit policy for it

This is not just a timeout bug. It is a missing runtime contract.

## 2. Design Requirements

The ACPX worker layer must satisfy all of these:

- **Bounded completion**
  - every worker turn ends with a clear terminal reason
- **Safe degradation**
  - a turn can fail cleanly without wedging the whole mission loop
- **No unbounded retries**
  - retries must be rare, classified, and capped
- **No session leaks**
  - repeated E2E runs must not accumulate abandoned ACPX sessions/processes
- **Prompt/runtime alignment**
  - output targets must not be mislabeled as mandatory reads
- **Strong observability**
  - terminal reason, retry reason, stall evidence, and cleanup outcome must be persisted

## 3. Options Considered

### Option A: Increase timeout and add more retries

Pros:

- minimal code churn

Cons:

- does not define completion
- can worsen acceptance runtime and hide hangs
- increases risk of repeated orphaned sessions

This is not acceptable.

### Option B: Keep session reuse, add event-driven completion and bounded degradation

Pros:

- smallest robust change
- compatible with current `AcpxWorkerHandleFactory`
- preserves session continuity for follow-up rounds
- gives explicit terminal reasons

Cons:

- requires a small state machine and new tests

This is the recommended option.

### Option C: Remove session reuse and always run ACPX in one-shot mode

Pros:

- simpler lifecycle

Cons:

- loses continuity benefits
- can increase startup overhead
- does not by itself fix prompt-envelope bugs

This is a possible fallback mode, not the primary design.

## 4. Recommended Design

Adopt **Option B** with one additional safety valve:

- primary mode: **reused ACPX session per packet**
- fallback mode: **fresh replacement session once**, only for classified transient failures

The system should not keep spawning fresh processes indefinitely.

## 5. Runtime Model

Introduce an explicit worker-turn model inside `AcpxWorkerHandle`.

### 5.1 Worker turn state machine

States:

- `idle`
- `starting`
- `running`
- `completed`
- `stalled`
- `degraded`
- `closed`

Terminal reasons:

- `process_exit_success`
- `process_exit_failure`
- `event_completed`
- `idle_timeout`
- `absolute_timeout`
- `reconnect_required`
- `fatal_tool_failure`
- `cancelled`

`BuilderResult.metadata` and `builder_report.json` should include:

- `terminal_reason`
- `session_name`
- `event_count`
- `commands_completed`
- `files_changed`
- `retry_count`
- `session_reused`
- `session_recycled`

### 5.2 Completion contract

The worker turn should be considered complete by **either**:

1. subprocess exits normally, or
2. the runtime sees enough evidence of completion and then reaches a bounded quiet period

"Enough evidence of completion" initially means:

- at least one meaningful mutation or verification event has completed
- no in-flight tool call remains active
- no new event arrives during `completion_quiet_period_seconds`

This avoids waiting forever on a process that has effectively finished useful work.

### 5.3 Timer model

Do not rely on one giant absolute timeout.

Use three timers:

- `startup_timeout_seconds`
  - no meaningful ACPX event after launch
- `idle_progress_timeout_seconds`
  - worker emits no progress event for too long while still running
- `absolute_timeout_seconds`
  - hard stop for the whole turn

Recommended baseline:

- startup: 20-30s
- idle progress: 45-90s
- absolute: keep current 1800s default for long tasks, but most failures should terminate earlier via startup/idle logic

## 6. Retry And Degradation Policy

Retries must be explicit and narrow.

### 6.1 Retry budget

Per worker turn:

- `max_retries = 1`

Per mission round packet:

- no more than one recycled ACPX session

### 6.2 Retry only for transient classes

Retryable:

- `reconnect_required`
- `startup_timeout` with zero useful events

Non-retryable:

- prompt-envelope contradiction detected
- fatal tool failure after useful work began
- repeated idle stall on recycled session
- verification failure

### 6.3 Retry safety

Before retrying on a fresh session:

- kill current subprocess
- cancel ACPX session
- mark handle unhealthy
- create a fresh session name

If there were already file changes, **do not auto-retry blindly**. Return a degraded failure so the supervisor can reason over partial work rather than replaying mutations.

## 7. Session Reuse And Cleanup

### 7.1 Reuse policy

Reuse ACPX session only within the same packet lineage, to preserve continuity across follow-up rounds.

But make reuse bounded:

- `max_turns_per_session`
- `max_session_age_seconds`
- `health = healthy | degraded | closed`

If a session crosses age/turn threshold, rotate it before the next send.

### 7.2 Cleanup policy

The system must guarantee all three cleanup paths:

- per-turn cleanup on timeout/degrade
- per-round cleanup on orchestrator abort
- global cleanup on factory `close_all()`

`close_all()` should remain the last-resort bulk cleanup, not the only cleanup.

### 7.3 Process discipline

Every `send()` call starts one subprocess. That is fine.

What must not happen:

- subprocess lives forever without bounded detection
- failed session is reused after reconnect-required state
- repeated E2E runs accumulate hidden ACPX sessions

## 8. Prompt Envelope Fixes

Prompt structure is part of robustness.

### 8.1 Separate read targets from create targets

`files_in_scope` cannot automatically become `Files to Read`.

Add a distinction:

- `files_to_read`
- `files_to_create_or_modify`

For mission packets:

- if a target path does not exist in the workspace, it must not be rendered under `Files to Read`
- new-file scaffold packets should render output targets under a different section, such as `## Target Files`

### 8.2 Envelope validation

Before launching ACPX:

- if prompt says "create file X" and `Files to Read` also contains X while X does not exist, log a prompt-contract warning and normalize the envelope before dispatch

This prevents avoidable first-step read failures.

## 9. Observability Requirements

Persist the following alongside existing worker telemetry:

- `worker_turn.json`
  - turn id
  - session id
  - terminal reason
  - retry reason
  - timers hit
  - event summary
- `worker_health.json`
  - session health
  - last successful progress timestamp
  - turns completed on this session

This is necessary for repeated acceptance runs and for later operator audit.

## 10. Testing Strategy

This work should be TDD-driven.

### Unit tests

Add/expand tests for:

- completion via subprocess exit
- completion via event + quiet period
- startup timeout with zero useful events
- idle progress timeout after partial progress
- reconnect-required stderr causing degraded failure
- single fresh-session retry on transient failure
- no retry after file mutation begins
- prompt-envelope normalization for new-file packets

### Integration tests

Add focused mission-worker tests for:

- scaffold packet on nonexistent target path
- worker that produces tool events but never exits
- worker that exits only after reconnect-required stderr

### E2E acceptance

Re-run:

- `tests/e2e/mission_start_acceptance.sh --full`
- `tests/e2e/exploratory_acceptance_smoke.sh --full`

Acceptance target:

- no indefinite hang
- explicit degraded failure if ACPX cannot complete
- fresh status page reflects terminal reason

## 11. Implementation Order

### Task 1: Add worker-turn state and terminal reasons

Files:

- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Test: `tests/unit/test_acpx_worker_handle.py`

### Task 2: Add progress-aware completion and bounded timers

Files:

- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Possibly create: `src/spec_orch/services/workers/acpx_worker_runtime.py`
- Test: `tests/unit/test_acpx_worker_handle.py`

### Task 3: Add retry classification and session recycling

Files:

- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle_factory.py`
- Test: `tests/unit/test_acpx_worker_handle.py`

### Task 4: Fix mission prompt envelope semantics

Files:

- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/run_controller.py`
- Test: `tests/unit/test_round_orchestrator.py`

### Task 5: Add observability artifacts and stability reporting integration

Files:

- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Modify: `src/spec_orch/services/stability_acceptance.py`
- Test: `tests/unit/test_stability_acceptance.py`

### Task 6: Re-run real E2E acceptance

Commands:

- `./tests/e2e/mission_start_acceptance.sh --full`
- `./tests/e2e/exploratory_acceptance_smoke.sh --full`
- `./tests/e2e/update_stability_acceptance_status.sh`

## 12. Success Criteria

This design is complete only when:

- mission-start no longer hangs indefinitely on ACPX worker turns
- exploratory acceptance no longer hangs indefinitely on ACPX worker turns
- every ACPX worker turn ends with an explicit terminal reason
- retries are bounded and visible
- unhealthy sessions are not reused
- new-file packets no longer instruct ACPX to read nonexistent targets by default
- repeated E2E runs do not accumulate unreaped ACPX sessions/processes
