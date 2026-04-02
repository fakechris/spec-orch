# Concurrency and Admission Control Program

> **Date:** 2026-04-01
> **Status:** draft v0
> **Intent:** define the first explicit concurrency topology and admission-control
> contract for SpecOrch, aligned with the conversational intake layer and the
> operator-workbench program.

## 1. Why This Program Exists

SpecOrch now has a much clearer semantic architecture:

- conversational intake and acceptance authoring define how work enters the system
- the intake-to-workspace handoff defines when work is ready for execution
- the operator workbench program defines how execution, judgment, and learning
  become operator-visible

What is still underspecified is the execution topology that sits underneath
those layers:

- which business objects may run concurrently
- which execution layers must remain serial
- which resources are limited and how they are budgeted
- how the daemon should reject, defer, or degrade work when budgets are exhausted

This program exists to define that topology before making large implementation
changes.

## 2. Relationship to the Existing Program

This program is not a replacement for the existing workbench or intake roadmap.
It is a substrate contract that supports them.

### Upstream connections

- conversational intake
- canonical issue and acceptance schema
- intake-to-workspace handoff

Those layers determine when a workspace subject is ready to enter execution.

### Primary downstream connections

- `SON-370` Shared Operator Semantics
- `SON-374` Runtime and Execution Substrate
- `SON-379` Decision and Judgment Substrate
- `SON-384` Execution Workbench v1

Practical meaning:

- the intake layer decides what work is eligible to run
- the concurrency program decides how much eligible work may run at once
- the execution substrate enforces those limits
- the workbenches expose the resulting queue, health, and contention state to operators

## 3. Design Goals

The first version of the concurrency model should satisfy these goals:

1. allow issue- and mission-level throughput to scale beyond a single active job
2. keep mission internals predictable and debuggable by preserving serial wave execution
3. make resource pressure explicit instead of relying on incidental process failure
4. model resource budgets as first-class objects that survive future runtime rewrites
5. make admission and refusal decisions operator-visible and auditable

## 4. Current Reality

Today the codebase is mixed, but the main supervised path is mostly serial:

- the daemon main loop is synchronous and advances work sequentially
- mission supervised execution dispatches packets serially inside a wave
- there is a separate asyncio-based plan execution path, but it is not the main
  operator-supervised mission path
- ACPX-backed workers use subprocesses and helper threads, so resource pressure
  often appears first as process/session pressure rather than pure Python thread pressure

The result is that current bottlenecks are not yet dominated by Python runtime
limits. They are dominated by:

- undefined concurrency boundaries
- unbounded subprocess/session growth risk
- weak admission control
- inconsistent observability around queue pressure and resource saturation

## 5. Core Model

### 5.1 Business-level concurrency

Business objects may run concurrently:

- `Issue Run`
- `Mission`

This is the primary concurrency layer. It maps to the operator expectation that
the system may work on multiple independent issues or missions at the same time.

### 5.2 Mission-level execution

Mission internals remain conservative in v1:

- rounds are serial
- waves are serial
- packets inside a wave are serial

This is an explicit design choice, not an accident.

Rationale:

- packet dependencies are still often implicit
- verification, scope, transcript, and evidence seams are easier to reason about
  when packet order is stable
- supervisor decisions remain more explainable when the system is not also
  reconciling concurrent packet side effects

### 5.3 Worker/session model

Mission execution always goes through a worker abstraction, but not every mission
uses ACPX.

The worker layer therefore needs its own resource model:

- ACPX session-backed workers
- local or one-shot builder workers
- verifier subprocesses
- browser evaluators

These should not inherit unlimited scale from business-level concurrency.

## 6. First-Class Resource Objects

The system should treat the following objects as canonical resource concepts.

### 6.1 Business capacity

- `IssueSlot`
- `MissionSlot`
- `RunSlot`

These express how many independent business subjects may be active at once.

### 6.2 Execution capacity

- `RoundSlot`
- `PacketSlot`

These express how much in-progress supervised work the runtime may advance at once.

### 6.3 Worker capacity

- `WorkerProcessSlot`
- `AcpxSessionSlot`
- `LiveTurnSlot`

These express how much live worker/session state the runtime may sustain.

### 6.4 Verification/tool capacity

- `VerificationProcessSlot`
- `BrowserEvaluatorSlot`
- `TypecheckSlot`
- `GitOperationSlot`

These express pressure from the auxiliary tooling that accompanies execution.

### 6.5 Shared control objects

- `ResourceBudget`
- `ResourceLease`
- `AdmissionDecision`
- `QueuePosition`
- `PressureSignal`

These should become the reusable vocabulary across runtime, dashboard, and future
language/runtime implementations.

## 7. Admission Control Contract

Admission control should answer a single question:

> Is the system willing and able to start or continue this unit of work now?

Every admission decision should produce one of these outcomes:

- `admit`
- `defer`
- `reject`
- `degrade`

### 7.1 `admit`

The subject receives the required leases and may proceed immediately.

### 7.2 `defer`

The subject is eligible to run, but the required budget is temporarily exhausted.
It remains queued with an explicit reason.

### 7.3 `reject`

The subject is not eligible to run because a prerequisite contract is not met.

Examples:

- workspace is not ready
- acceptance is incomplete
- blocking unresolved questions remain

### 7.4 `degrade`

The subject may proceed, but only under a reduced execution mode.

Examples:

- browser evaluation is skipped because the browser budget is exhausted
- a fallback worker/runtime is used because ACPX session budget is exhausted
- a lower-cost judgment path is selected during pressure

## 8. Default v1 Policy

### 8.1 Concurrency topology

The first policy should be explicit:

- issues may run concurrently
- missions may run concurrently
- each mission may have only one active round at a time
- each round may have only one active wave at a time
- each wave executes packets serially

### 8.2 Resource ownership

Budgets should be modeled at two scopes:

- global daemon budget
- per-subject budget

#### Global daemon budget

Examples:

- total active issue runs
- total active missions
- total ACPX sessions
- total verification subprocesses
- total browser evaluators

#### Per-subject budget

Examples:

- one active round per mission
- one active wave per round
- one packet at a time inside a wave

### 8.3 Suggested initial defaults

These values are placeholders for the first implementation tranche:

- `max_active_issues = 2`
- `max_active_missions = 2`
- `max_total_active_runs = 4`
- `max_active_rounds = 2`
- `packet_parallelism_per_wave = 1`
- `max_acpx_sessions = 2`
- `max_worker_processes = 4`
- `max_verification_processes = 4`
- `max_browser_evaluators = 1`

The exact defaults may change, but the policy shape should not.

## 9. Operator-Visible Behavior

This program should make the following operator-visible states explicit:

- queued because business capacity is full
- deferred because execution capacity is full
- degraded because a lower execution mode was chosen
- blocked because the handoff contract or readiness contract failed
- saturated because a concrete resource budget is exhausted

These states belong in the operator-facing execution substrate and workbench
surfaces. They should not be inferred indirectly from stale timestamps or silent
non-progress.

## 10. Alignment With Intake and Workspace Handoff

The intake layer and the concurrency layer should divide responsibility cleanly.

### Intake / handoff owns

- canonical issue creation
- acceptance authoring
- readiness and unresolved-question status
- the decision that a workspace may or may not be created

### Concurrency / admission control owns

- whether a ready workspace subject may start now
- whether it must queue
- whether it must run in degraded mode
- whether execution pressure requires explicit backoff

### Rule

The system must not use admission control to paper over bad intake readiness.

Examples:

- missing acceptance is not a queue problem
- blocking ambiguity is not a capacity problem
- malformed workspace handoff is not a scheduler problem

Those remain `reject` or `handoff_failed` conditions.

## 11. Alignment With the Workbenches

### Execution Workbench

This program is primarily an Execution Workbench substrate concern.

The workbench should eventually expose:

- active issue/mission inventory
- queue inventory
- per-subject admission state
- pressure and saturation signals
- available operator interventions

### Judgment Workbench

Judgment should remain aware of degraded execution modes.

Examples:

- a run judged under missing browser evidence
- a comparison produced under reduced verification budget
- a finding produced while the system was in degraded mode

### Learning Workbench

Learning should preserve the operational context of repeated failures.

Examples:

- repeated queue saturation patterns
- repeated degraded-mode executions
- repeated ACPX session exhaustion

These are not just runtime details. They can become learning signals.

## 12. Observability Contract

Every admission or resource decision should be reconstructible from canonical
artifacts.

Minimum fields:

- `subject_id`
- `subject_kind`
- `decision`
- `required_budgets`
- `granted_budgets`
- `queue_position`
- `pressure_reason`
- `degrade_reason`
- `recorded_at`

This contract should be reusable across:

- runtime artifacts
- dashboard execution surfaces
- future showcase/timeline APIs

## 13. Implementation Strategy

This program should be delivered in phases.

### Phase 1: semantics and policy

- define the vocabulary and contract
- define the default topology
- define the default budgets
- document rejection, deferral, and degradation behavior

### Phase 2: runtime substrate

- introduce explicit budget objects and resource leasing
- enforce admission decisions in daemon/mission entry points
- add queue and pressure reporting to runtime seams

### Phase 3: operator visibility

- expose queue, pressure, and intervention state in Execution Workbench surfaces
- expose degraded-mode evidence in Judgment Workbench

### Phase 4: optional selective parallelism

Only after the serial policy is stable should the system consider opening:

- limited packet parallelism inside a wave
- class-based packet concurrency
- role-specific worker pools

That work is intentionally out of scope for v1.

## 14. Recommended Linear Breakdown

### Epic

`SON-412` `[Epic] Concurrency Model and Admission Control`

### Child issues

1. `SON-413` `Define canonical concurrency topology for issue, mission, round, wave, and packet`
2. `SON-414` `Define resource budget object model and admission decision contract`
3. `SON-415` `Document default daemon budgets and degraded-mode policy`
4. `SON-416` `Add runtime seams for queue state, pressure signals, and admission records`
5. `SON-417` `Enforce mission and issue admission control at daemon entry points`
6. `SON-418` `Expose queue and pressure state in Execution Workbench surfaces`

## 15. Done Criteria

This program is successful when:

- the system has one explicit concurrency topology instead of implicit behavior
- business-level concurrency is intentional and bounded
- mission internals remain predictably serial in v1
- resource budgets are first-class and visible
- admission decisions are operator-visible and auditable
- the model can be carried forward even if the runtime implementation later moves from Python to another language
