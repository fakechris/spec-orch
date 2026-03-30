# Runtime Glossary

> Status: current-state terminology baseline
> Date: 2026-03-29
> Scope: terminology only; no target design decisions

## Purpose

This glossary normalizes the runtime vocabulary used across spec-orch docs and code.

It exists to prevent one recurring failure mode:

- the same word means different things in different subsystems
- different words refer to the same runtime object

This document defines the **current preferred meanings** of key runtime terms.
It does **not** redesign the system.

## Rules For Using This Glossary

1. Prefer the definitions in this document over informal usage in older docs.
2. If a term is overloaded in code, call that out explicitly instead of silently reusing it.
3. If a doc needs a different meaning, it must define that meaning locally and explain why.

## Session

### Preferred meaning

A **Session** is a reusable execution identity that can receive more work over time without being recreated from scratch.

### What counts as a Session today

- a worker session identified by `session_id` in supervised mission execution
- an ACPX-backed persistent worker session
- a vendor-owned upstream session identifier when explicitly labeled as vendor session

### What does not count as a Session

- `report.json`
- `progress.json`
- a workspace directory by itself
- a single one-shot builder invocation

### Current code anchors

- [`WorkerHandle.session_id`](../../src/spec_orch/domain/protocols.py)
- [`AcpxWorkerHandle`](../../src/spec_orch/services/workers/acpx_worker_handle.py)
- [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py)

### Notes

Issue-centric execution is currently **session-like**, but not truly session-centric.
Its continuity is file-backed, not modeled as a first-class `Session` object.

## Run

### Preferred meaning

A **Run** is one full execution attempt over one issue pipeline in one workspace under one `run_id`.

### What a Run includes

- flow selection
- spec gating or spec freeze handling
- builder execution
- verification
- review bootstrap or review reuse
- gate evaluation
- run-level report/artifact persistence

### Current code anchors

- [`RunController.run_issue()`](../../src/spec_orch/services/run_controller.py)
- [`TelemetryService.new_run_id()`](../../src/spec_orch/services/telemetry_service.py)
- [`RunReportWriter`](../../src/spec_orch/services/run_report_writer.py)

### Primary identifiers

- `run_id`
- `issue_id`
- workspace path

### Canonical persistent representation

- preferred: `run_artifact/live.json`
- legacy bridge: `report.json`

## Round

### Preferred meaning

A **Round** is one supervised execute-review-decide cycle inside mission-centric execution.

### What a Round includes

- dispatching the current wave's workers
- collecting worker results
- collecting verification / gate / visual / acceptance artifacts
- supervisor review
- recording one `RoundDecision`

### Current code anchors

- [`RoundSummary`](../../src/spec_orch/domain/models.py)
- [`RoundDecision`](../../src/spec_orch/domain/models.py)
- [`RoundOrchestrator.run_supervised()`](../../src/spec_orch/services/round_orchestrator.py)

### Primary identifiers

- `mission_id`
- `round_id`
- `wave_id`

### Canonical persistent representation

- `rounds/round-XX/round_summary.json`
- `rounds/round-XX/round_decision.json`

## Mission

### Preferred meaning

A **Mission** is the cross-issue contract that defines what should be delivered and why.

### What a Mission owns

- title
- spec
- acceptance criteria
- constraints
- execution plan lineage
- mission lifecycle

### Current code anchors

- [`Mission`](../../src/spec_orch/domain/models.py)
- [`MissionLifecycleManager`](../../src/spec_orch/services/lifecycle_manager.py)
- [`MissionService`](../../src/spec_orch/services/mission_service.py)

### Canonical persistent representation

- `docs/specs/<mission_id>/spec.md`
- mission-local operator and round artifacts under `docs/specs/<mission_id>/`

### Notes

Mission is a contract-layer object, not an execution attempt.
Multiple runs and multiple rounds may occur under one mission.

## Worker Session

### Preferred meaning

A **Worker Session** is a session owned by one mission worker, usually scoped to one work packet.

### Current code shape

Today this is typically named:

- `mission-<mission_id>-<packet_id>`

### Current code anchors

- [`RoundOrchestrator._dispatch_wave()`](../../src/spec_orch/services/round_orchestrator.py)
- [`SessionOps`](../../src/spec_orch/domain/models.py)
- [`WorkerHandleFactory`](../../src/spec_orch/domain/protocols.py)

### Notes

Use **Worker Session** when you need to distinguish it from:

- issue run continuity
- vendor session ids
- mission lifecycle state

## Execution Unit

### Preferred meaning

An **Execution Unit** is the smallest object the runtime intends to send to an execution owner.

### What counts as an Execution Unit today

- an [`Issue`](../../src/spec_orch/domain/models.py) in the issue-centric path
- a [`WorkPacket`](../../src/spec_orch/domain/models.py) in the mission-centric path

### What does not count as an Execution Unit

- a `Mission`
- a `Run`
- a `Round`
- a `WorkerHandle`

### Notes

Use this term when you want the shared abstraction above `Issue` and `WorkPacket`
without claiming they are already the same runtime object.

## Execution Attempt

### Preferred meaning

An **Execution Attempt** is one concrete try to advance one Execution Unit under one owner and one continuity model.

### What counts as an Execution Attempt today

- one issue `Run` under `RunController`
- one packet execution under `PacketExecutor`
- one worker send for one packet in one mission round

### What an Execution Attempt includes

- one owner
- one execution context
- one result object or failure outcome

### Notes

This is intentionally broader than `Run`.
`Run` remains the preferred term for the issue-centric full pipeline attempt.
Use `Execution Attempt` when comparing issue and mission paths at the same abstraction level.

## Execution Owner

### Preferred meaning

An **Execution Owner** is the runtime component responsible for driving an Execution Attempt and deciding when that attempt is complete from its local perspective.

### Current examples

- [`RunController`](../../src/spec_orch/services/run_controller.py)
- [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py)
- [`ParallelRunController`](../../src/spec_orch/services/parallel_run_controller.py)
- [`PacketExecutor`](../../src/spec_orch/domain/protocols.py)
- [`WorkerHandle`](../../src/spec_orch/domain/protocols.py) for local packet execution only

### What an Execution Owner is not

- not the contract object
- not the artifact carrier
- not the shell entrypoint

### Notes

Use this term when the confusion is specifically about ownership.
For example: `Issue` is an object, `RunController` is its current execution owner.

## Supervisor

### Preferred meaning

A **Supervisor** is the component that reviews execution evidence and decides the next action for a broader loop.

### What counts as a Supervisor today

- the [`SupervisorAdapter`](../../src/spec_orch/domain/protocols.py) used by mission rounds
- the broader supervision role exercised through [`RoundOrchestrator`](../../src/spec_orch/services/round_orchestrator.py) plus `RoundDecision`

### What does not count as a Supervisor

- a builder adapter
- a packet executor
- a worker handle

### Notes

Use `Supervisor` for the mission round decision role.
Do not use it as a synonym for generic review, gate, or lifecycle management.

## Worker

### Preferred meaning

A **Worker** is the execution-facing actor that performs implementation work for one Execution Unit.

### What counts as a Worker today

- a mission worker behind [`WorkerHandle`](../../src/spec_orch/domain/protocols.py)
- a one-shot worker via [`OneShotWorkerHandle`](../../src/spec_orch/services/workers/oneshot_worker_handle.py)
- an ACPX-backed persistent worker via [`AcpxWorkerHandle`](../../src/spec_orch/services/workers/acpx_worker_handle.py)

### Notes

Use `Worker` when you mean the actor doing the implementation.
Use `Worker Session` when you mean the reusable continuity identity for that worker.

## Artifact Carrier

### Preferred meaning

An **Artifact Carrier** is the persisted file or directory that stores an object's state or evidence so another component can reopen it later.

### Current examples

- `report.json`
- `run_artifact/live.json`
- `run_artifact/manifest.json`
- `round_summary.json`
- `round_decision.json`
- `.spec_orch_runs/lifecycle_state.json`

### What an Artifact Carrier is not

- not the runtime object itself
- not the execution owner
- not the full evidence model

### Notes

Use this term when a discussion risks collapsing an object into its file representation.
For example: `RoundDecision` is the object; `round_decision.json` is the carrier.

## Continuity

### Preferred meaning

**Continuity** is the mechanism by which an execution path preserves reusable context or resumable identity across attempts.

### Current examples

- file-backed issue run continuity
- worker session continuity
- one-shot worker continuity with no durable identity
- subprocess packet continuity with process-local scope only

### Notes

Use `Continuity` when the real question is not “what object is this?” but “how does this path keep going without starting from zero?”

## Continuity Kind

### Preferred meaning

A **Continuity Kind** is the categorized form of continuity used by an `ExecutionAttempt`.

### Current working values

- `file_backed_run`
- `worker_session`
- `oneshot_worker`
- `subprocess_packet`

### Notes

`continuity_kind` should explain the reuse model.
It should not be overloaded to encode success, failure, or supervision.

## Supervision Cycle

### Preferred meaning

A **Supervision Cycle** is a higher-level control loop that evaluates one or more `ExecutionAttempt`s and decides the next action.

### What counts as a Supervision Cycle today

- one mission `Round`

### What does not count as a Supervision Cycle

- a single issue `Run`
- a packet execution attempt
- a worker session

### Notes

Use this term when the discussion is about oversight, aggregation, and decision-making.
Do not collapse it into `ExecutionAttempt`.

## Artifact

### Preferred meaning

An **Artifact** is any persisted output that another runtime component can reopen by path.

### Examples

- spec snapshot
- builder report
- explain report
- review report
- deviations log
- round summary
- browser evidence
- visual evaluation

### What is not automatically an Artifact

- an in-memory event
- a transient Python object
- a log line that is not persisted to a file

### Current code anchors

- [`ArtifactManifest`](../../src/spec_orch/domain/models.py)
- [`RunArtifactService`](../../src/spec_orch/services/run_artifact_service.py)
- [`ArtifactService`](../../src/spec_orch/services/artifact_service.py)

## Manifest

### Preferred meaning

A **Manifest** is the indexed catalog of artifacts for one execution context.

### Current preferred usage

Unless otherwise noted, `Manifest` should mean the canonical artifact index under:

- `run_artifact/manifest.json`

### Current bridge usage

There is also a compatibility bridge:

- `artifact_manifest.json`

### Current code anchors

- [`RunArtifactService._build_manifest()`](../../src/spec_orch/services/run_artifact_service.py)
- [`RunReportWriter.write_artifact_manifest()`](../../src/spec_orch/services/run_report_writer.py)

### Notes

When writing docs, do not say "manifest" without stating whether you mean:

- canonical run artifact manifest
- legacy compatibility manifest
- mission round artifact list

## Decision Point

### Preferred meaning

A **Decision Point** is a named place in the runtime where one authority must choose among multiple valid next actions.

### Current authority categories

- `rule_owned`
- `llm_owned`
- `human_required`

### Notes

Use **Decision Point** for the reusable slot in the runtime.
Do not use it for one specific historical choice.

## Decision Record

### Preferred meaning

A **Decision Record** is the persisted record of one choice made at one Decision Point.

### What it should capture

- which point was exercised
- which authority owned the choice
- what action was selected
- what confidence and blocking questions were present

### Notes

Use **Decision Record** for one concrete event, not for the general policy of a subsystem.

## Intervention

### Preferred meaning

An **Intervention** is the explicit handoff from automated runtime control to a human-required action.

### Current primary form

- approval or clarification prompts surfaced through the approvals queue

### Notes

An Intervention is not the same thing as a pause.
A mission may pause for many reasons, but an Intervention specifically means a human-facing decision request has been raised.

## Fallback

### Preferred meaning

A **Fallback** is a degraded but intentional alternative path taken when the preferred path is unavailable, invalid, or unsafe.

### Current categories of fallback

| Category | Example |
|---|---|
| routing fallback | LLM route selection falls back to static mapping |
| service fallback | memory service unavailable, continue without memory |
| environment fallback | API key / base env fallback resolution |
| persistence fallback | local JSONL queue used when remote creation fails |
| observability fallback | explicit fallback event emitted to the event bus |

### What Fallback is not

- not a single state object
- not the same thing as resume
- not the same thing as checkpoint
- not the same thing as legacy compatibility

### Current code anchors

- [`EventBus.emit_fallback()`](../../src/spec_orch/services/event_bus.py)
- [`emit_fallback_safe()`](../../src/spec_orch/services/event_bus.py)
- [`FlowRouter`](../../src/spec_orch/flow_engine/flow_router.py)
- [`litellm_profile.py`](../../src/spec_orch/services/litellm_profile.py)
- conductor local fork fallback in [`conductor.py`](../../src/spec_orch/services/conductor/conductor.py)

## Related Terms

### Workspace

A **Workspace** is the filesystem location where execution happens.
It is not automatically a Session, Run, or Mission.

Primary owner:

- [`WorkspaceService`](../../src/spec_orch/services/workspace_service.py)

### Checkpoint

A **Checkpoint** is persisted progress that helps resume later work.

Current primary example:

- `progress.json` via [`RunProgressSnapshot`](../../src/spec_orch/services/run_progress.py)

Checkpoint is narrower than Session and narrower than Run.

### Lifecycle

A **Lifecycle** is a state machine governing one object family.

Current distinct lifecycles:

- issue run lifecycle
- mission lifecycle
- round lifecycle
- plan lifecycle
- evolution lifecycle

Do not say "the lifecycle" unless the object family is obvious.

## Preferred Usage Table

| If you mean... | Prefer saying... | Avoid saying... |
|---|---|---|
| one issue pipeline attempt | Run | session |
| smallest executable object in either spine | Execution Unit | issue-like thing, packet-like thing |
| one concrete try under one owner | Execution Attempt | run, loop, pass |
| runtime component that owns the try | Execution Owner | object, state |
| reusable worker identity | Worker Session | run |
| implementation actor | Worker | session |
| reuse model across attempts | Continuity Kind | session, mode |
| mission round decision role | Supervisor | reviewer, orchestrator, owner |
| higher-level oversight loop | Supervision Cycle | round-like execution |
| reusable runtime choice slot | Decision Point | approval, decision |
| one concrete persisted choice | Decision Record | review, note |
| human handoff object | Intervention | pause, approval |
| mission contract and its state | Mission | run |
| one supervised cycle | Round | pass, attempt, loop |
| file carrying persisted state/evidence | Artifact Carrier | object, state |
| persisted output file reopened later | Artifact | log, state, thing |
| artifact index file | Manifest | report |
| degraded alternate path | Fallback | state |

## Current Ambiguities We Are Intentionally Preserving

This glossary does not erase current implementation ambiguity.
It only gives us a stable way to talk about it.

The following remain true today:

- issue execution still behaves like a session in some places without modeling one
- `report.json` still acts as a bridge even though newer artifact files exist
- fallback remains an overloaded family of concepts in code
- multiple lifecycle state machines coexist

## Use In Future Docs

Before writing any refactor or architecture decision document, use this glossary to answer:

1. Which object is being discussed: Mission, Run, Round, or Session?
2. Which persistent file is canonical?
3. Is a fallback being proposed, observed, or persisted?
4. Is the proposed owner runtime-local, mission-local, or system-wide?
