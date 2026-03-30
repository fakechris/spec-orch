# Architecture Recovery

> Status: current-state recovery document, not a target design
> Date: 2026-03-29

## Purpose

This document answers one question: **what architecture does spec-orch actually have today?**

It does **not** propose a new design yet.
It recovers the current runtime model from code and existing docs so we can:

- align narrative and code ownership
- identify the real runtime spine
- define a shared vocabulary before any large refactor

## Scope

This recovery focuses on:

- the declared Seven Planes narrative
- the actual runtime ownership in code
- the current meanings of `Session`, `Executor`, `Scheduler`, `Lifecycle`, `Web Harness`, and `Fallback`
- the current persistence model and canonical file sources

Primary sources:

- [`VISION.zh.md`](../../VISION.zh.md)
- [`docs/architecture/seven-planes.md`](./seven-planes.md)
- [`docs/architecture/2026-03-19-directional-review.zh.md`](./2026-03-19-directional-review.zh.md)
- [`docs/reviews/2026-03-20-architecture-deep-review.md`](../reviews/2026-03-20-architecture-deep-review.md)
- [`src/spec_orch/services/run_controller.py`](../../src/spec_orch/services/run_controller.py)
- [`src/spec_orch/services/round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py)
- [`src/spec_orch/services/lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py)
- [`src/spec_orch/services/run_report_writer.py`](../../src/spec_orch/services/run_report_writer.py)
- [`src/spec_orch/services/run_artifact_service.py`](../../src/spec_orch/services/run_artifact_service.py)
- [`src/spec_orch/domain/models.py`](../../src/spec_orch/domain/models.py)
- [`src/spec_orch/domain/protocols.py`](../../src/spec_orch/domain/protocols.py)

## Executive Summary

spec-orch currently has a **clear architecture narrative** but **no single canonical runtime model**.

The docs describe a Seven Planes system:

- Contract
- Task
- Harness
- Execution
- Evidence
- Control
- Evolution

But the code does not implement those planes as runtime-owned packages or objects.
Instead, the system is currently held together by **two parallel orchestration spines**:

1. **Issue-centric spine**
   - centered on [`RunController`](../../src/spec_orch/services/run_controller.py)
   - owns single-issue spec freeze, execution, verification, review bootstrap, gate, and report persistence

2. **Mission-centric spine**
   - centered on [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py) and [`MissionLifecycleManager`](../../src/spec_orch/services/lifecycle_manager.py)
   - owns wave/round supervision, worker session reuse, acceptance, visual QA, and mission lifecycle

This split is the main reason why both of these are true at once:

- the narrative is rich
- the ownership is blurry

## 1. Declared Architecture vs Actual Architecture

### 1.1 Declared Architecture

The declared architecture is stable across docs:

- [`VISION.zh.md`](../../VISION.zh.md) defines Seven Planes as the system philosophy
- [`seven-planes.md`](./seven-planes.md) maps code to the seven planes
- [`2026-03-19-directional-review.zh.md`](./2026-03-19-directional-review.zh.md) already notes that some planes may remain enhancement layers rather than mandatory runtime layers

The declared intent is:

- Contract freezes intent
- Task decomposes work
- Harness stabilizes execution
- Execution runs isolated work
- Evidence proves completion
- Control operates the fleet
- Evolution improves the system

### 1.2 Actual Architecture

The actual runtime shape is simpler and messier:

- a domain model layer
- several large orchestrators
- multiple execution providers
- several file-backed state carriers
- a dashboard and operator surface
- an evolution subsystem

The deep review already states the key mismatch plainly:

- the Seven Planes are not reflected in the `services/` layout
- `RunController`, `cli.py`, and `daemon.py` still act as god objects

That means the Seven Planes currently function more as a **strategic map** than as an **enforced ownership map**.

## 2. The Actual Runtime Spine

### 2.1 Spine A: Issue-Centric Pipeline

The issue-centric path is centered on [`RunController`](../../src/spec_orch/services/run_controller.py).

In one object, it currently owns:

- issue loading
- workspace preparation
- flow resolution via `FlowRouter` or `FlowMapper`
- spec freeze / spec approval gating
- builder execution
- verification
- review initialization
- gate evaluation
- explain/report writing
- flow promotion/demotion/backtrack signaling
- checkpoint resume behavior

This is the main runtime spine for classic `run_issue()` style execution.

### 2.2 Spine B: Mission-Centric Supervised Execution

The mission-centric path is centered on:

- [`MissionLifecycleManager`](../../src/spec_orch/services/lifecycle_manager.py)
- [`MissionExecutionService`](../../src/spec_orch/services/mission_execution_service.py)
- [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py)

This path introduces concepts not native to the issue-centric path:

- wave-boundary supervision
- round summaries and round decisions
- session reuse / spawn / cancel
- worker handles
- acceptance evaluation
- browser evidence
- visual evaluation

This is the only path where `session_id` is truly first-class in our own runtime model.

## 3. Component Recovery

### 3.1 Session

`Session` is **not** a single canonical runtime primitive today.

Current meanings:

| Meaning | Current owner | Notes |
|---|---|---|
| Issue run continuity | [`report.json`](../../src/spec_orch/services/run_report_writer.py), [`progress.json`](../../src/spec_orch/services/run_progress.py) | file-backed state, not a `Session` object |
| Mission worker session | [`WorkerHandle.session_id`](../../src/spec_orch/domain/protocols.py) | real runtime session identity in supervised rounds |
| ACPX persistent session | [`AcpxWorkerHandle`](../../src/spec_orch/services/workers/acpx_worker_handle.py) | external session managed by ACPX |
| Vendor session id | builder adapters | for example Claude result `session_id`, not a spec-orch-owned session model |

Current conclusion:

- issue mode is **session-like**
- mission mode is **session-aware**
- the codebase is **not session-centric overall**

### 3.2 Executor

There is no single `Executor`.

Current execution ownership is split:

| Executor role | Current owner |
|---|---|
| single issue pipeline executor | [`RunController`](../../src/spec_orch/services/run_controller.py) |
| single packet executor | [`PacketExecutor` protocol](../../src/spec_orch/domain/protocols.py), [`packet_executor.py`](../../src/spec_orch/services/packet_executor.py) |
| wave executor | [`WaveExecutor` protocol](../../src/spec_orch/domain/protocols.py), [`wave_executor.py`](../../src/spec_orch/services/wave_executor.py) |
| mission worker executor | [`WorkerHandle.send()`](../../src/spec_orch/domain/protocols.py) |
| full plan executor | [`ParallelRunController`](../../src/spec_orch/services/parallel_run_controller.py) |

Conclusion:

- `Executor` exists as a family of concepts
- ownership is distributed by path, not unified by abstraction boundary

### 3.3 Scheduler

`Scheduler` is also distributed.

| Scheduling function | Current owner |
|---|---|
| issue pipeline step scheduling | `FlowEngine` + `RunController` |
| flow tier selection | `FlowRouter` / `FlowMapper` |
| mission phase scheduling | [`MissionLifecycleManager`](../../src/spec_orch/services/lifecycle_manager.py) |
| wave scheduling | `ParallelRunController` |
| round progression and retry/continue decisions | [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py) |
| worker session ops after a round | `RoundDecision.session_ops` |

Conclusion:

- there is scheduling logic
- there is no single scheduler object

### 3.4 Lifecycle

Lifecycle is one of the most duplicated concepts in the codebase.

Current lifecycle families:

| Lifecycle | Definition |
|---|---|
| issue run lifecycle | `RunState` in [`domain/models.py`](../../src/spec_orch/domain/models.py) |
| mission lifecycle | `MissionPhase` in [`lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py) |
| plan lifecycle | `PlanStatus` in [`domain/models.py`](../../src/spec_orch/domain/models.py) |
| round lifecycle | `RoundStatus` and `RoundAction` in [`domain/models.py`](../../src/spec_orch/domain/models.py) |
| evolution lifecycle | `LifecycleEvolver` protocol in [`domain/protocols.py`](../../src/spec_orch/domain/protocols.py) |

Conclusion:

- lifecycle is conceptually important
- lifecycle is not singular
- the codebase has multiple lifecycle state machines, each local to a subsystem

## 4. Seven Planes Recovered as Runtime Ownership

This is the most honest current mapping.

| Plane | Current status | Real owner today |
|---|---|---|
| Contract | fairly real | `SpecSnapshot`, mission/spec docs, Conductor, spec services |
| Task | partially real | `ExecutionPlan/Wave/WorkPacket`, scoper, parallel run controller |
| Harness | mostly fragmented | context assembler, compliance, flow router, builder preambles, configs |
| Execution | real but split | `RunController`, builders, worker handles, packet/wave executors |
| Evidence | real | gate, findings, report writer, run artifacts, telemetry, acceptance, visual |
| Control | real but UI-heavy | lifecycle manager, event bus, dashboard, CLI, daemon |
| Evolution | real but separate | evolvers and evolution trigger |

Key observation:

- Contract, Evidence, Control, Evolution are easiest to recognize as planes today.
- Harness is the least coherent plane in implementation.
- Execution is real, but it is split across two orchestration spines.

## 5. Web Harness Recovery

`Web Harness` is **not** one subsystem today.

It is spread across three families:

### 5.1 Operator Surface

Main ownership:

- [`src/spec_orch/dashboard/app.py`](../../src/spec_orch/dashboard/app.py)
- [`src/spec_orch/dashboard/routes.py`](../../src/spec_orch/dashboard/routes.py)
- [`src/spec_orch/dashboard/launcher.py`](../../src/spec_orch/dashboard/launcher.py)

This layer owns:

- dashboard HTML shell
- mission and approval APIs
- websocket event streaming
- launcher flows
- operator-facing tabs and mission detail views

### 5.2 Browser/Visual Evidence

Main ownership:

- [`src/spec_orch/services/acceptance/browser_evidence.py`](../../src/spec_orch/services/acceptance/browser_evidence.py)
- [`src/spec_orch/services/visual/playwright_visual_eval.py`](../../src/spec_orch/services/visual/playwright_visual_eval.py)

This layer owns:

- Playwright browser capture
- screenshots
- console/page errors
- route interaction traces
- browser evidence artifacts

### 5.3 Embedded Review Routes

Main ownership:

- [`RoundOrchestrator._build_acceptance_artifacts()`](../../src/spec_orch/services/round_orchestrator.py)

This layer embeds:

- review routes
- transcript links
- approval links
- visual QA links
- acceptance links

Conclusion:

- Web is important
- Web is operationally real
- Web Harness is currently **distributed**, not centrally owned

## 6. Persistence Recovery

Current persistence is file-backed and layered, but not yet normalized.

### 6.1 Current Persistent Files

| File | Current meaning | Owner |
|---|---|---|
| `report.json` | legacy run summary and state carrier | `RunReportWriter` |
| `run_artifact/live.json` | preferred unified persisted run payload | `RunArtifactService` |
| `run_artifact/manifest.json` | canonical artifact catalog | `RunArtifactService` |
| `artifact_manifest.json` | compatibility bridge manifest | `RunReportWriter` |
| `progress.json` | stage checkpoint / resume support | `RunProgressSnapshot` |
| `spec_snapshot.json` | frozen spec contract state | spec snapshot services |
| `.spec_orch_runs/lifecycle_state.json` | mission lifecycle state | `MissionLifecycleManager` |
| `telemetry/events.jsonl` | orchestrator event stream | telemetry services |
| `telemetry/incoming_events.jsonl` | raw builder/worker event stream | adapters / worker handles |
| `telemetry/activity.log` | operator-friendly timeline | activity logger |
| `rounds/round-XX/round_summary.json` | supervised round summary | `RoundOrchestrator` |
| `rounds/round-XX/round_decision.json` | supervised round decision | `RoundOrchestrator` |
| `rounds/round-XX/visual_evaluation.json` | visual evaluation result | `RoundOrchestrator` |
| `rounds/round-XX/browser_evidence.json` | browser evidence | acceptance/browser evidence |
| `rounds/round-XX/acceptance_review.json` | acceptance review | acceptance evaluator |

### 6.2 Canonical vs Bridge vs Timeline

Current practical classification:

| Type | Files |
|---|---|
| canonical run payload | `run_artifact/live.json` |
| canonical artifact index | `run_artifact/manifest.json` |
| legacy bridge | `report.json`, `artifact_manifest.json` |
| checkpoint state | `progress.json`, `lifecycle_state.json` |
| transcript/timeline evidence | `events.jsonl`, `incoming_events.jsonl`, `activity.log` |
| mission round state | `round_summary.json`, `round_decision.json` |

Important nuance:

[`RunReportWriter.load_persisted_run_payload()`](../../src/spec_orch/services/run_report_writer.py) already prefers `run_artifact/live.json` over `report.json`.
That means the codebase has already started to move toward a new canonical source, but compatibility bridges remain active.

## 7. Fallback Recovery

There is currently **no single object called `FallbackState`**.

The term `fallback` is overloaded and refers to multiple different things:

| Fallback meaning | Example |
|---|---|
| degraded execution path | `FlowRouter` falls back to static mapping |
| degraded capability path | missing memory service emits fallback event |
| environment lookup fallback | `litellm_profile` env resolution |
| local persistence fallback | conductor local fork JSONL |
| observability event | `EventBus.emit_fallback()` |

Current implication:

- fallback is an observability concept
- fallback is a degradation concept
- fallback is not yet a unified persistent state domain

## 8. Ownership Map

The following map answers: **who actually owns each critical concern today?**

| Concern | Primary owner | Secondary owners |
|---|---|---|
| issue runtime orchestration | `RunController` | `FlowEngine`, `FlowRouter`, `RunReportWriter` |
| mission runtime orchestration | `RoundOrchestrator` | `MissionLifecycleManager`, `MissionExecutionService` |
| mission state transitions | `MissionLifecycleManager` | `EventBus` |
| task decomposition model | `ExecutionPlan/Wave/WorkPacket` | scoper, plan parser |
| worker session lifecycle | `WorkerHandleFactory` + `WorkerHandle` | `RoundDecision.session_ops` |
| builder event ingestion | builder adapters / worker handles | telemetry |
| run checkpointing | `RunProgressSnapshot` | `RunController` |
| run summary persistence | `RunReportWriter` | `RunArtifactService` |
| artifact cataloging | `RunArtifactService` | `RunReportWriter` |
| operator web surface | dashboard modules | lifecycle manager, event bus |
| visual/browser proof | visual evaluator + browser evidence | `RoundOrchestrator` |
| fallback observability | `EventBus` / `RunEventLogger` | individual services |

Ownership verdict:

- some concerns have a clear owner
- many concerns have both a primary owner and a bridge owner
- bridges are the main source of narrative drift

## 9. Comparison to External Systems

### 9.1 Compared to open-harness

[`open-harness`](https://github.com/MaxGfeller/open-harness) has a cleaner runtime split:

- `Agent`
- `Session`
- middleware
- subagents
- instructions
- skills

spec-orch does not currently have that single runtime axis.
It has richer delivery concepts, but more fragmented runtime ownership.

### 9.2 Compared to AgentScope

[`AgentScope`](https://github.com/agentscope-ai/agentscope) has clearer framework abstractions:

- state
- session
- plan
- hooks
- pipelines

spec-orch is stronger on delivery integrity and evidence/control concepts, but weaker on having one stable framework object model for runtime execution.

## 10. What This Recovery Says

This recovery supports five conclusions:

1. The Seven Planes are currently a **valid strategic narrative**, not yet a strict code architecture.
2. The runtime is currently split between an **issue-centric** spine and a **mission-centric** spine.
3. `Session`, `Executor`, `Scheduler`, and `Lifecycle` are all **plural concepts**, not singular runtime objects.
4. Web Harness is **distributed across dashboard, visual, and acceptance subsystems**.
5. Persistence is already moving toward a unified artifact model, but legacy bridges are still active and still shape ownership.

## 11. Immediate Use of This Document

This document should be treated as the baseline for any future refactor discussion.

Before proposing new architecture, we should require all future discussions to answer against this recovery:

- Which current spine does the proposal replace, preserve, or merge?
- Which current persistent file becomes canonical, deprecated, or bridged?
- Which current meanings of `Session` are being collapsed or preserved?
- Which current owner loses responsibility, and where does that responsibility move?

## 12. Recommended Next Artifact

The next document should **not** be a target architecture yet.

It should be a narrower follow-up:

- `runtime-glossary.md`

That glossary should normalize the exact meanings of:

- Session
- Run
- Round
- Mission
- Worker Session
- Artifact
- Manifest
- Fallback
- Lifecycle

Only after that glossary is stable should we write the refactor decision doc.
