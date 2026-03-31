# Runtime Chain Observability Epic

> **Linear:** `SON-339`
> **Status (2026-03-31):** Epic created in Linear. `SON-340` is in progress. `SON-341` through `SON-345` are backlog.

> **Positioning note (2026-03-31):** This epic is now one slice of the broader
> runtime package absorption program defined in
> `docs/plans/2026-03-31-runtime-package-absorption-plan.md`. Runtime chain
> observability remains the right starting seam because it improves diagnosis
> efficiency immediately, but it should no longer be treated as the entire
> runtime package story.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unified runtime-chain observability substrate so any issue, mission, round, packet, supervisor review, and acceptance run can be traced live and queried after the fact.

**Architecture:** Build this as a runtime-level support seam, not as ad hoc logging. Phase 1 lands the chain substrate, heartbeat/status model, and CLI/harness query surfaces. Phase 2 adds dashboard visualization on top of the same chain data without changing the underlying truth model.

**Tech Stack:** Python 3.13, `runtime_core`, file-backed telemetry, `AcpxWorkerHandle`, `RoundOrchestrator`, `RunController`, supervisor/acceptance adapters, FastAPI dashboard, shell-based e2e harnesses, Linear.

## 1. Why This Is A Dedicated Epic

Real E2E runs surfaced a program-level weakness:

- ACPX worker telemetry exists, but it is local and not surfaced as a unified run view
- supervisor and acceptance phases do not emit equivalent live heartbeat/status data
- current runs have many local `run_id` values, but no single root chain that ties together:
  - issue run
  - mission run
  - round
  - packet
  - supervisor review
  - acceptance graph/review
  - replay/exploratory follow-up

This is no longer just a debugging concern. It is runtime infrastructure.

## 2. Desired End State

For any live or historical run, the operator should be able to answer:

- what root execution chain is active
- which phase is currently running
- which child span last progressed
- whether the system is healthy, stalled, degraded, or finished
- which artifacts prove the current state
- which ACPX session, worker turn, supervisor call, or acceptance graph step belongs to this chain

The answer should come from one canonical substrate, not from manually stitching together multiple logs.

## 3. Scope

### In scope

- root `chain_id` and parent/child span lineage
- chain events and current chain status snapshots
- phase heartbeat for worker, supervisor, acceptance, and replay paths
- CLI and harness query/tail surfaces
- mission/issue/e2e integration on top of the chain substrate
- dashboard visualization only after the substrate is stable

### Out of scope

- replacing existing normalized execution artifacts
- changing business semantics in `runtime_core` / `decision_core`
- unbounded tracing backends or external telemetry platforms

## 4. Two-Phase Delivery

### Phase 1: Runtime chain substrate

This phase solves diagnosis efficiency first.

Deliverables:

- canonical runtime chain models
- append-only chain event log
- current chain status snapshot
- live heartbeat/status emission from:
  - ACPX worker turns
  - round orchestration
  - supervisor review
  - acceptance graph/evaluator
  - replay/exploratory acceptance flows
- CLI and shell query surfaces that can answer “what is happening right now?”

Completion criteria:

- `mission_start_acceptance.sh --full` can show current runtime phase without manual artifact spelunking
- stalled runs produce explicit terminal or degraded reasons
- fresh E2E investigations no longer require opening multiple unrelated logs to identify the waiting phase

### Phase 2: Dashboard observability surfaces

This phase comes last.

Deliverables:

- dashboard runtime chain view
- chain timeline and child-span summaries
- linkouts to worker telemetry, round summaries, acceptance graph artifacts, and fixture seeds
- visible degraded/stalled indicators for operator review

Completion criteria:

- dashboard can render the same chain truth that CLI/harness can query
- no dashboard-only state exists; UI is read-only over the chain substrate

## 5. Canonical Model

The minimum chain model should include:

- `chain_id`
- `span_id`
- `parent_span_id`
- `subject_kind`
  - `issue`
  - `mission`
  - `round`
  - `packet`
  - `supervisor`
  - `acceptance`
  - `replay`
- `subject_id`
- `phase`
  - `started`
  - `heartbeat`
  - `completed`
  - `failed`
  - `degraded`
  - `cancelled`
- `status_reason`
- `session_refs`
- `artifact_refs`
- `updated_at`

The minimum file-backed carriers should be:

- `chain_events.jsonl`
- `chain_status.json`

## 6. Task Breakdown

### Task 1: Define runtime-chain models and carriers

**Files:**
- Create: `src/spec_orch/runtime_chain/__init__.py`
- Create: `src/spec_orch/runtime_chain/models.py`
- Create: `src/spec_orch/runtime_chain/store.py`
- Test: `tests/unit/test_runtime_chain_models.py`
- Test: `tests/unit/test_runtime_chain_store.py`

**Deliverables:**
- chain event and status models
- append-only event writer
- current status snapshot writer/reader

### Task 2: Add root chain and span lineage across issue and mission paths

**Files:**
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle.py`
- Modify: `src/spec_orch/services/workers/acpx_worker_handle_factory.py`
- Test: `tests/unit/test_run_controller.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_acpx_worker_handle.py`

**Deliverables:**
- root `chain_id` issuance
- parent/child span wiring for round and packet execution
- worker-turn spans linked to the active chain

### Task 3: Add phase heartbeat for supervisor and acceptance

**Files:**
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Modify: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Modify: `src/spec_orch/acceptance_runtime/runner.py`
- Test: `tests/unit/test_litellm_supervisor_adapter.py`
- Test: `tests/unit/test_litellm_acceptance_evaluator.py`
- Test: `tests/unit/test_acceptance_runtime_runner.py`

**Deliverables:**
- start/heartbeat/completion/degraded events for long in-process phases
- explicit wait-state reasons for model-bound review/evaluation phases

### Task 4: Add CLI and harness query surfaces

**Files:**
- Create: `src/spec_orch/cli/runtime_chain_commands.py`
- Modify: `src/spec_orch/cli/__init__.py`
- Modify: `tests/e2e/mission_start_acceptance.sh`
- Modify: `tests/e2e/exploratory_acceptance_smoke.sh`
- Test: `tests/unit/test_runtime_chain_cli.py`
- Test: `tests/unit/test_stability_acceptance.py`

**Deliverables:**
- CLI query/tail/status commands
- e2e harnesses that report current chain phase instead of appearing silent

### Task 5: Integrate chain status into acceptance reporting

**Files:**
- Modify: `src/spec_orch/services/stability_acceptance.py`
- Modify: `tests/e2e/update_stability_acceptance_status.sh`
- Modify: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Test: `tests/unit/test_stability_acceptance.py`

**Deliverables:**
- acceptance status page includes latest chain state references
- failures and degraded runs link to the exact active span or terminal reason

### Task 6: Dashboard observability surfaces (Phase 2)

**Files:**
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/transcript.py`
- Create/Modify: `tests/unit/test_dashboard_api.py`
- Create/Modify: `tests/unit/test_dashboard_missions.py`

**Deliverables:**
- dashboard runtime chain surface
- timeline and span drilldown backed by chain files

## 7. Linear Breakdown

Create one new epic:

- `[Epic] Runtime Chain Observability and Live Traceability`

Create these initial child issues:

1. `SON-340` `Define runtime chain models and status carriers`
2. `SON-341` `Wire root chain lineage across issue and mission execution`
3. `SON-342` `Add supervisor and acceptance phase heartbeat`
4. `SON-343` `Add runtime chain CLI and harness status commands`
5. `SON-344` `Integrate runtime chain status into stability acceptance reporting`
6. `SON-345` `Add dashboard runtime chain surfaces`

## 8. Completion Gate

This epic should only be considered complete when:

- a single chain model covers issue, mission, round, packet, supervisor, acceptance, and replay
- long-running phases emit visible heartbeat or degraded state
- shell and CLI users can identify the current wait point without manual log spelunking
- stability acceptance reports link to chain status and terminal reasons
- dashboard surfaces, if enabled, read the same chain truth without introducing a second state system
