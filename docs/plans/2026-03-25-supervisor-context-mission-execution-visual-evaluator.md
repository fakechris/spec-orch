# Supervisor Context, Mission Execution, and Visual Evaluator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve supervised mission execution quality by enriching supervisor context, converging mission execute ownership, and adding a pluggable visual evaluation hook.

**Architecture:** Introduce a single `MissionExecutionService` that owns mission plan loading, supervised execution, and execution summaries. Refactor daemon and lifecycle manager to consume that service rather than separately orchestrating mission execution. Enrich `RoundOrchestrator` and `LiteLLMSupervisorAdapter` with first-class mission/spec/telemetry context plus optional visual evaluation artifacts.

**Tech Stack:** Python 3.13, Typer CLI, dataclasses, existing `RoundOrchestrator`, `ContextAssembler`, ACPX worker handles, LiteLLM supervisor.

## Scope

This plan intentionally combines three previously separate improvements because they share the same seam:

1. richer supervisor context
2. mission execute path convergence
3. visual evaluator design and first wiring

The implementation is split into small, verifiable batches.

### Task 1: Add domain types for mission execution and visual evaluation

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Modify: `src/spec_orch/domain/protocols.py`
- Test: `tests/unit/test_round_models.py`
- Test: `tests/unit/test_pluggable_adapters.py`

**Step 1: Write failing tests**

Add tests for:
- `VisualEvaluationResult` round-trips and serializes artifacts
- `MissionExecutionResult` preserves pause/completion/summary metadata
- `VisualEvaluatorAdapter` protocol accepts a stub implementation

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest -q tests/unit/test_round_models.py tests/unit/test_pluggable_adapters.py
```

Expected: missing types / protocol failures

**Step 3: Write minimal implementation**

Add:
- `VisualEvaluationResult`
- `MissionExecutionResult`
- `VisualEvaluatorAdapter`

Keep the schema minimal:
- visual evaluation is optional
- mission execution result contains summary text and round result state, not daemon-specific side effects

**Step 4: Run tests to verify they pass**

Run the same pytest command.

### Task 2: Introduce MissionExecutionService and make it the execution owner

**Files:**
- Create: `src/spec_orch/services/mission_execution_service.py`
- Modify: `src/spec_orch/services/lifecycle_manager.py`
- Modify: `src/spec_orch/services/daemon.py`
- Test: `tests/unit/test_lifecycle_manager.py`
- Test: `tests/unit/test_daemon_mission.py`

**Step 1: Write failing tests**

Add tests for:
- lifecycle manager delegates mission execution to `MissionExecutionService`
- daemon delegates mission execution to `MissionExecutionService`
- pause/completed/max-rounds states are derived from service results, not duplicated logic
- execution summary text is returned by the service and reused by daemon

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest -q tests/unit/test_lifecycle_manager.py tests/unit/test_daemon_mission.py
```

Expected: assertions show direct `run_supervised`/`load_plan` calls instead of service usage

**Step 3: Write minimal implementation**

`MissionExecutionService` should:
- load the mission plan
- call `RoundOrchestrator.run_supervised(...)` when supervisor exists
- fall back to `ParallelRunController.run_plan(...)` otherwise
- return a `MissionExecutionResult` with:
  - `completed`
  - `paused`
  - `max_rounds_hit`
  - `rounds`
  - `summary_markdown`
  - `blocking_questions`

`MissionLifecycleManager` should:
- consume the service for `_do_execute`
- remain the phase owner

`SpecOrchDaemon` should:
- consume the service in `_execute_mission`
- keep Linear comments / state updates / event bus emission as daemon-only side effects

**Step 4: Run tests to verify they pass**

Run the same pytest command.

### Task 3: Enrich supervisor context with mission metadata and packet telemetry

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Modify: `src/spec_orch/services/mission_service.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_litellm_supervisor_adapter.py`

**Step 1: Write failing tests**

Add tests for:
- supervisor context includes mission acceptance criteria and constraints
- prompt payload includes packet telemetry paths / builder report paths / activity log paths
- supervisor context loads mission spec text instead of synthetic issue-only metadata

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest -q tests/unit/test_round_orchestrator.py tests/unit/test_litellm_supervisor_adapter.py
```

Expected: prompt payload missing mission/spec/telemetry data

**Step 3: Write minimal implementation**

`RoundOrchestrator` should:
- load `Mission` via `MissionService`
- build a real `Issue` context for supervisor assembly
- include packet workspace artifact paths in `RoundArtifacts`

`LiteLLMSupervisorAdapter` should:
- stop dumping only raw JSON blobs
- build a structured payload that includes:
  - mission summary
  - spec text excerpt
  - mission acceptance criteria / constraints
  - round history summary
  - worker telemetry pointers
  - optional visual evaluation result

**Step 4: Run tests to verify they pass**

Run the same pytest command.

### Task 4: Add pluggable visual evaluator hook and no-op implementation

**Files:**
- Create: `src/spec_orch/services/visual/noop_visual_evaluator.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_litellm_supervisor_adapter.py`

**Step 1: Write failing tests**

Add tests for:
- round orchestrator calls visual evaluator when configured
- visual evaluation artifacts are persisted into `round_summary.json` / supervisor payload
- no-op evaluator leaves behavior unchanged

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest -q tests/unit/test_round_orchestrator.py tests/unit/test_litellm_supervisor_adapter.py
```

**Step 3: Write minimal implementation**

Add a `NoopVisualEvaluator` that returns `None`.

Wire visual evaluation into the flow after worker execution and before supervisor review:
- `RoundOrchestrator` collects packet workspace inputs
- evaluator returns a `VisualEvaluationResult | None`
- result is attached to `RoundArtifacts`

Do not add browser runtime dependency in this batch.
This batch is only the seam plus persistence.

**Step 4: Run tests to verify they pass**

Run the same pytest command.

### Task 5: Add docs and run full verification

**Files:**
- Modify: `docs/reference/spec-orch-toml.md`
- Modify: `docs/guides/supervised-mission-e2e-playbook.md`
- Modify: `docs/agent-guides/services.md`

**Step 1: Document**

Document:
- mission execution ownership
- visual evaluator hook
- richer supervisor context behavior

**Step 2: Run full verification**

Run:

```bash
uv run --python 3.13 python -m ruff check src/ tests/
uv run --python 3.13 python -m ruff format --check src/ tests/
uv run --python 3.13 python -m mypy src/spec_orch/
uv run --python 3.13 python -m pytest tests/unit/ -v --tb=short --ignore=tests/unit/test_codex_harness_builder_adapter.py
uv run --python 3.13 python -c "print('build ok')"
```

Expected:
- all lint/typecheck/test/build commands pass

### Notes for implementation

- `MissionExecutionService` should be a service, not another manager/state machine
- daemon remains the owner of Linear comments and external writeback
- lifecycle manager remains the owner of mission phase transitions
- `RoundOrchestrator` remains the owner of execute-review-decide logic
- visual evaluator in this batch is a seam, not a full Playwright runtime

### Recommended commit sequence

1. `feat: add mission execution and visual evaluation domain models`
2. `refactor: converge mission execution through shared service`
3. `feat: enrich supervisor context with mission and telemetry data`
4. `feat: add pluggable visual evaluator hook`
5. `docs: document supervised mission execution and visual evaluation`
