# Mission Supervisor Round Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a supervised multi-round execute-review-decide loop to Mission `EXECUTING`, so SpecOrch can run worker rounds, review their artifacts, and dynamically choose the next action.

**Architecture:** Use `docs/specs/mission-supervisor-round-loop/plan.md` as the architecture source of truth. Implement the feature incrementally: define shared round-domain types first, then add supervisor and worker protocols, then land a minimal `RoundOrchestrator`, then wire lifecycle/daemon/session behavior. Keep `MissionLifecycleManager` as the phase owner and move execution logic into a separate service.

**Tech Stack:** Python, dataclasses, runtime-checkable protocols, pytest, existing `ContextAssembler`, mission lifecycle state, ACPX/Codex adapters.

---

## Source Of Truth

- Architecture/design: `docs/specs/mission-supervisor-round-loop/plan.md`
- Executable implementation plan: this file

## Batch Strategy

- Batch 1: domain types and protocols
- Batch 2: supervisor adapter skeleton and supervisor context node
- Batch 3: minimal round orchestrator with one-shot worker handles
- Batch 4: lifecycle integration for `EXECUTING`
- Batch 5: ACPX-backed persistent worker handles
- Batch 6: daemon wiring and `inject_btw` bugfix

This order deliberately separates:
- control-plane abstractions from runtime behavior
- one-shot supervised rounds from ACPX session continuity
- lifecycle wiring from daemon/config plumbing

### Task 1: Define Round Domain Types

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Create: `tests/unit/test_round_models.py`

**Step 1: Write the failing tests**

Add tests for:

```python
def test_round_decision_roundtrip_with_plan_patch() -> None: ...

def test_round_summary_roundtrip_with_decision() -> None: ...

def test_round_decision_to_dict_omits_plan_patch_when_absent() -> None: ...
```

Validate:
- `RoundAction` serializes to string values
- `SessionOps` and `PlanPatch` survive round-trip conversion
- `RoundSummary` restores nested `RoundDecision`

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_round_models.py -q`

Expected: FAIL because the round-domain models do not exist yet.

**Step 3: Write the minimal implementation**

Add to `src/spec_orch/domain/models.py`:
- `RoundStatus`
- `RoundAction`
- `SessionOps`
- `PlanPatch`
- `RoundDecision`
- `RoundArtifacts`
- `RoundSummary`

Implementation notes:
- Follow the structure in `docs/specs/mission-supervisor-round-loop/plan.md`
- Keep rich analysis out of the dataclasses; only carry orchestration intent
- Add `to_dict()` / `from_dict()` only where persistence is required

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_round_models.py -q`

Expected: PASS.

### Task 2: Define Worker/Supervisor Protocols

**Files:**
- Modify: `src/spec_orch/domain/protocols.py`
- Modify: `tests/unit/test_pluggable_adapters.py`

**Step 1: Write the failing tests**

Add runtime protocol tests for:

```python
def test_stub_worker_handle_is_worker_protocol() -> None: ...

def test_stub_supervisor_adapter_is_supervisor_protocol() -> None: ...

def test_stub_worker_factory_is_factory_protocol() -> None: ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_pluggable_adapters.py -q`

Expected: FAIL because the new protocols do not exist yet.

**Step 3: Write the minimal implementation**

Add to `src/spec_orch/domain/protocols.py`:
- `WorkerHandle`
- `SupervisorAdapter`
- `WorkerHandleFactory`

Implementation notes:
- `WorkerHandle.send()` should return `BuilderResult`
- `SupervisorAdapter.review_round()` should accept `RoundArtifacts`, `ExecutionPlan`, `list[RoundSummary]`
- Keep protocols runtime-checkable

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_pluggable_adapters.py -q`

Expected: PASS.

### Task 3: Add Supervisor Context Registration

**Files:**
- Modify: `src/spec_orch/services/context/node_context_registry.py`
- Modify: `tests/unit/test_context_assembler.py`

**Step 1: Write the failing tests**

Add a test that:
- `get_node_context_spec("supervisor")` succeeds
- the spec asks for execution-heavy context needed for review

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_context_assembler.py -q`

Expected: FAIL because `supervisor` is not registered.

**Step 3: Write the minimal implementation**

Register a `supervisor` node context entry with:
- task fields for spec/constraints
- execution fields for diff, verification, gate, builder events, review
- learning fields for recent failures

Do not overfit token budget; prefer parity with reviewer/scoper scale.

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_context_assembler.py -q`

Expected: PASS.

### Task 4: Add Minimal One-Shot Worker Handles

**Files:**
- Create: `src/spec_orch/services/workers/oneshot_worker_handle.py`
- Create: `src/spec_orch/services/workers/in_memory_worker_handle_factory.py`
- Create: `tests/unit/test_worker_handles.py`

**Step 1: Write the failing tests**

Cover:

```python
def test_one_shot_worker_handle_delegates_to_builder_adapter() -> None: ...

def test_in_memory_factory_reuses_session_id_handle() -> None: ...

def test_factory_close_all_closes_every_handle() -> None: ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_worker_handles.py -q`

Expected: FAIL because the worker handle implementations do not exist.

**Step 3: Write the minimal implementation**

Implementation rules:
- `OneShotWorkerHandle` wraps an injected `BuilderAdapter`
- each `send()` constructs an `Issue` from prompt + workspace context
- `cancel()` is a no-op
- `close()` marks handle closed / performs lightweight cleanup
- `InMemoryWorkerHandleFactory` keeps a simple `dict[str, WorkerHandle]`

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_worker_handles.py -q`

Expected: PASS.

### Task 5: Add Minimal RoundOrchestrator

**Files:**
- Create: `src/spec_orch/services/round_orchestrator.py`
- Create: `tests/unit/test_round_orchestrator.py`

**Step 1: Write the failing tests**

Cover the smallest useful loop:

```python
def test_run_supervised_continues_to_next_wave_until_complete() -> None: ...

def test_run_supervised_pauses_on_ask_human() -> None: ...

def test_run_supervised_retries_same_wave_when_decision_is_retry() -> None: ...
```

Use fake:
- `SupervisorAdapter`
- `WorkerHandleFactory`
- `ContextAssembler`

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_round_orchestrator.py -q`

Expected: FAIL because `RoundOrchestrator` does not exist.

**Step 3: Write the minimal implementation**

Land:
- `RoundOrchestrator`
- `RoundOrchestratorResult`
- history persistence under `docs/specs/<mission_id>/rounds/round-XX/`
- simple wave-boundary loop only

Do not implement mid-packet interruption in this batch.

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_round_orchestrator.py -q`

Expected: PASS.

### Task 6: Wire Mission Lifecycle To RoundOrchestrator

**Files:**
- Modify: `src/spec_orch/services/lifecycle_manager.py`
- Modify: `tests/unit/test_lifecycle_manager.py`

**Step 1: Write the failing tests**

Cover:

```python
def test_auto_advance_executes_via_round_orchestrator() -> None: ...

def test_mission_state_round_fields_roundtrip() -> None: ...

def test_auto_advance_marks_failed_when_max_rounds_exhausted() -> None: ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_lifecycle_manager.py -q`

Expected: FAIL because lifecycle manager has no execute-stage orchestrator hook.

**Step 3: Write the minimal implementation**

Add:
- `current_round`
- `round_orchestrator_state`
- optional injected `round_orchestrator`
- `_do_execute()`

Behavior:
- if no orchestrator is injected, preserve old behavior
- if result completes, transition to `ALL_DONE`
- if paused, remain in `EXECUTING`
- if max rounds exhausted, mark failed

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_lifecycle_manager.py -q`

Expected: PASS.

### Task 7: Add LiteLLM Supervisor Adapter Skeleton

**Files:**
- Create: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Create: `tests/unit/test_litellm_supervisor_adapter.py`

**Step 1: Write the failing tests**

Cover:

```python
def test_supervisor_adapter_parses_round_decision_from_model_output() -> None: ...

def test_supervisor_adapter_falls_back_to_ask_human_on_parse_error() -> None: ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_litellm_supervisor_adapter.py -q`

Expected: FAIL because the adapter does not exist.

**Step 3: Write the minimal implementation**

Support:
- injected `chat_completion` callable for easy testing
- writing `supervisor_review.md`
- writing `round_decision.json`
- fallback `RoundAction.ASK_HUMAN` when parsing fails

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_litellm_supervisor_adapter.py -q`

Expected: PASS.

### Task 8: Add ACPX Worker Handles

**Files:**
- Create: `src/spec_orch/services/workers/_acpx_utils.py`
- Create: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Create: `src/spec_orch/services/workers/acpx_worker_handle_factory.py`
- Modify: `src/spec_orch/services/builders/acpx_builder_adapter.py`
- Create: `tests/unit/test_acpx_worker_handle.py`

**Step 1: Write the failing tests**

Cover:
- session-based prompt dispatch
- session ensure-on-first-use
- factory reuse by session id

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_acpx_worker_handle.py -q`

Expected: FAIL because the ACPX worker handle layer does not exist.

**Step 3: Write the minimal implementation**

Rules:
- extract shared ACPX command/event helpers
- keep `AcpxBuilderAdapter` public interface unchanged
- make worker handles mission-scoped and resumable by session id

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_acpx_worker_handle.py -q`

Expected: PASS.

### Task 9: Daemon Wiring And `inject_btw` Bugfix

**Files:**
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `tests/unit/test_daemon_mission.py`
- Modify: `tests/unit/test_run_controller.py`

**Step 1: Write the failing tests**

Cover:

```python
def test_daemon_builds_round_orchestrator_when_supervisor_config_present() -> None: ...

def test_render_builder_envelope_includes_btw_context() -> None: ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_daemon_mission.py tests/unit/test_run_controller.py -q`

Expected: FAIL because daemon does not build the new stack and builder envelope ignores `btw_context.md`.

**Step 3: Write the minimal implementation**

Add:
- daemon factory wiring for supervisor + worker factory + round orchestrator
- `btw_context.md` inclusion in `_render_builder_envelope()`

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_daemon_mission.py tests/unit/test_run_controller.py -q`

Expected: PASS.

## Current Execution Cut

This session should implement:
- Task 1
- Task 2
- Task 3 if Task 1-2 land cleanly and verification stays green

Stop and reassess before starting `RoundOrchestrator` if:
- protocol shapes need revision after tests
- context registry constraints expose missing fields
- lifecycle manager assumptions need earlier adjustment
