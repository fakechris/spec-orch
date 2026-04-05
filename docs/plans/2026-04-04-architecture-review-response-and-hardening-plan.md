# Architecture Review Response And Hardening Plan

Date: 2026-04-04
Owner: Codex
Scope: Merge and respond to:
- `docs/reviews/ARCHITECTURE_AUDIT_REPORT.md`
- `docs/reviews/ARCHITECTURE_REVIEW.md`

## Why This Document Exists

The two review documents are directionally correct, but they overlap heavily. This document converts them into a single execution view:

- every numbered finding is responded to
- overlapping items are merged
- already-covered items are called out explicitly
- low-priority or deferred items are justified
- the remaining work is ordered into a concrete implementation mainline

This is not a new architecture proposal. It is a hardening and sequencing document against the current `main`.

## Current Baseline On `main`

Current baseline already includes:

- conversational intake and handoff (`SON-408..411`)
- shared semantics, runtime substrate, judgment substrate (`SON-370`, `SON-374`, `SON-379`)
- execution, judgment, learning workbenches (`SON-384`, `SON-390`, `SON-396`)
- surface cleanup and showcase narrative initial waves (`SON-402`, `SON-363`)
- admission governor tranche 1 and tranche 2
- memory/context layering tranche 1
- verification independence tranche 1
- structural judgment tranche 2
- learning promotion discipline tranche 2
- acceptance hardening protocol tranche 1
- self-hosting Linear sync and dogfood wave 1

That means several review concerns are already partially addressed at the semantics, acceptance, and dogfood layers. The remaining work is concentrated in runtime safety, state coherence, contract hardening, and module decomposition.

## Merged Response To Review Findings

### 1. Daemon Poller/Executor Coupling And Round God Object

Sources:
- `ARCHITECTURE_AUDIT_REPORT.md` item 1
- `ARCHITECTURE_REVIEW.md` issue 1
- `ARCHITECTURE_REVIEW.md` sections 4.1, 6.1, 7.1.2

Current state:
- Still open.
- `RoundOrchestrator` remains the main coordination sink.
- daemon still drives execution synchronously enough that long worker operations reduce the value of admission/concurrency policy.
- `SON-412` improved policy visibility and governor semantics, but it did not yet fully decouple polling from execution.

Decision:
- Must fix.

Priority:
- `P0`

Why now:
- This is still the main reliability and maintainability bottleneck.
- It blocks real concurrency and makes later adapter/runtime expansion expensive.

Planned response:
- split `RoundOrchestrator` into narrower carriers first
- then decouple daemon poll/triage from execution dispatch
- only after that push toward true parallel wave execution

### 2. Daemon State Persistence, Locks, Crash Recovery, Retry Semantics

Sources:
- `ARCHITECTURE_AUDIT_REPORT.md` item 2
- `ARCHITECTURE_REVIEW.md` issue 2
- `ARCHITECTURE_REVIEW.md` sections 6.1, 6.2, 6.3, 6.4
- `ARCHITECTURE_REVIEW.md` section 7.3 item 1

Current state:
- Still open.
- `main` has heartbeat and better governor semantics, but daemon state is still file-backed:
  - `daemon_state.json`
  - per-issue lock files
  - `retry_at` files
- process-level singleton protection is still not strong enough.

Decision:
- Must fix.

Priority:
- `P0`

Why now:
- This is the most direct production reliability hole left in the runtime.
- Current self-hosting and daemon dogfooding make this more urgent, not less.

Planned response:
- move daemon issue-state to SQLite WAL
- introduce PID/process singleton protection plus lease-style in-progress ownership
- unify retry and recovery bookkeeping into one durable per-issue row

### 3. Mission Lifecycle Split: `MissionStatus` vs `MissionPhase`

Sources:
- `ARCHITECTURE_REVIEW.md` issue 3
- `ARCHITECTURE_REVIEW.md` section 5.4
- `ARCHITECTURE_REVIEW.md` section 7.3 item 2

Current state:
- Still open.
- The problem is real on current `main`.
- `MissionStatus` is still used in domain/service surfaces while `MissionPhase` drives lifecycle progression.
- Some current code already contains coercion glue, which proves the mismatch is still active rather than solved.

Decision:
- Must fix.

Priority:
- `P0`

Why now:
- It is a single-source-of-truth problem.
- It directly affects Linear sync, dashboard state, and self-hosting workflow interpretation.

Planned response:
- make `MissionPhase` the canonical internal lifecycle
- reduce `MissionStatus` to a derived or external-facing projection
- enforce explicit phase-to-status projection in one place only

### 4. Verification Semantics: `skipped` Cannot Mean `pass`

Sources:
- `ARCHITECTURE_REVIEW.md` issue 4

Current state:
- Still open on current `main`.
- Acceptance/browser evidence gained richer step markers in the recent hardening wave.
- But `VerificationService` still records unconfigured steps as pass-like booleans.

Decision:
- Must fix.

Priority:
- `P1`

Why not before items 1-3:
- It is correctness-important, but it does not threaten daemon integrity the way runtime persistence and lifecycle drift do.
- It can be fixed in a bounded tranche once the runtime state line is under control.

Planned response:
- introduce explicit verification outcome semantics:
  - `pass`
  - `fail`
  - `skipped`
- propagate them through reports, memory, learning, and gate consumers

### 5. Context Inflation, Memory API Sprawl, And Context/Memory Boundary Drift

Sources:
- `ARCHITECTURE_AUDIT_REPORT.md` item 3
- `ARCHITECTURE_REVIEW.md` issue 5
- `ARCHITECTURE_REVIEW.md` issue 7
- `ARCHITECTURE_REVIEW.md` sections 4.4, 7.1.1

Current state:
- Partially addressed, not finished.
- Current `main` already has:
  - context taxonomy language
  - memory/context layering tranche 1
  - learning discipline tranche 2
- But runtime assembly still depends on heavy eager calls, truncation is still crude, and `MemoryService` remains too broad and too singleton-oriented.

Decision:
- Must continue.

Priority:
- `P1`

Why not P0:
- The system now has a usable taxonomy and better discipline already.
- The remaining risk is quality/performance/evolvability, not immediate production corruption.

Planned response:
- split query and command sides for memory
- make `ContextAssembler` diff-aware and file-aware instead of raw string slicing
- enforce layered context handles:
  - Active Context
  - Working State
  - Review Evidence
  - Archive
  - Promoted Learning

### 6. Artifact Schema, Event Payload Contracts, Telemetry Facade, And Filesystem Isolation

Sources:
- `ARCHITECTURE_AUDIT_REPORT.md` item 4
- `ARCHITECTURE_REVIEW.md` sections 5.2, 5.3, 6.5, 7.3 item 3

Current state:
- Partially addressed, not finished.
- Current `main` already has:
  - stronger acceptance artifact sanitization
  - release bundle discipline
  - step-level browser evidence markers
  - better observability artifacts
- But it still lacks:
  - one canonical workspace artifact schema
  - typed event payload contracts
  - one telemetry write facade
  - stronger verification isolation

Decision:
- Must continue.

Priority:
- `P1`

Why not P0:
- Artifact hygiene is much better than before.
- The biggest remaining risk is still runtime state and orchestration coupling.

Planned response:
- add canonical workspace schema
- narrow event payload shapes
- centralize telemetry writes behind one facade
- evaluate shadow-checkout verification as a later tranche, after state substrate hardening

### 7. RunController Dependency Sprawl, Protocol Bypass, Adapter Registry, DI

Sources:
- `ARCHITECTURE_REVIEW.md` issue 6
- `ARCHITECTURE_REVIEW.md` sections 4.2, 5.1, 7.2, 8.3

Current state:
- Largely open.
- Some adapter seams exist and self-hosting Linear sync improved structured mirror flows.
- But `RunController` still knows too many concrete implementations and the project still relies on singleton/lazy-global patterns in key areas.

Decision:
- Must address, but after runtime state and lifecycle cleanup.

Priority:
- `P2`

Why lower:
- This is mostly a leverage and evolvability problem.
- It becomes much easier to do correctly once runtime state and orchestrator boundaries are cleaner.

Planned response:
- introduce `RunControllerConfig`
- move default adapter construction out of controller internals
- add adapter registry
- later, introduce application-scoped DI for memory/runtime/adapter seams

### 8. Gate Verdict Mixing Mergeability With Flow Control

Sources:
- `ARCHITECTURE_REVIEW.md` issue 8

Current state:
- Real concern, still open.
- Not the first bottleneck.

Decision:
- Defer.

Priority:
- `P2`

Reason for defer:
- This API split is worthwhile, but it is easier and safer after mission lifecycle and controller/orchestrator boundaries are cleaner.
- Doing it too early risks churn across several already-stabilized surfaces.

Planned response:
- split `GateVerdict` into:
  - merge decision
  - flow-control signal
- do this together with controller/orchestrator contract cleanup

### 9. Re-export Shims, `services/` Package Reorg, `_core` Package Cleanliness

Sources:
- `ARCHITECTURE_REVIEW.md` issues 9 and 10
- `ARCHITECTURE_REVIEW.md` sections 4.1, 4.3
- `ARCHITECTURE_REVIEW.md` section 8.1

Current state:
- Still true.
- The shims and package sprawl are real.
- But they are not the highest live failure source.

Decision:
- Do not lead with this.

Priority:
- `P3`

Reason for lower priority:
- Removing shims and reorganizing modules improves architecture hygiene, but it does not by itself fix the runtime failure modes.
- It should piggyback on the bigger decomposition waves, not precede them.

Planned response:
- remove re-export shims while moving real owners into clearer packages
- keep `_core` packages only where they become true kernels
- do not do a cosmetic package shuffle first

## Explicit “Already Covered Enough” Calls

These findings are directionally valid, but do not justify standalone new architecture work right now:

1. `_core` packages as conceptual staging areas
- True observation.
- Not a first-order bottleneck.
- Action: only clean these as part of adjacent contract moves.

2. “Need a whole new architecture for acceptance hardening”
- Not needed.
- Recent `main` already added exploratory planning contract, browser step markers, failure artifact fields, and acceptance review discipline.
- Action: continue hardening through existing seams, not a new subsystem.

3. “Need to redesign showcase/surface first”
- Not needed.
- Current bottlenecks are runtime and contract integrity, not missing UI.

## Priority-Ordered Mainline

### Priority 0: Runtime Safety And Canonical Lifecycle

1. Daemon state substrate migration
- SQLite WAL-backed daemon state
- per-issue durable state row
- retry and recovery state unified
- PID/process singleton lock
- lease/heartbeat-based ownership

2. Mission lifecycle unification
- `MissionPhase` becomes canonical internal state
- `MissionStatus` becomes projection only
- one authoritative projection layer for dashboard/Linear/external surfaces
- transition validation enforced at write boundaries

3. Round/daemon boundary split
- extract `WaveDispatcher`
- extract `AcceptancePipeline`
- extract round state carrier
- daemon poller becomes triage/enqueue, not long synchronous executor

### Priority 1: Contract Hardening

4. Verification outcome semantics
- `pass/fail/skipped`
- no more “not configured = pass”
- propagate into reports, learning, and gate inputs

5. Context/materialization hardening
- `MemoryReader` / `MemoryWriter` split
- diff-aware context assembly
- truncated-file metadata and explicit omission reporting
- layered context handles instead of eager heavy blobs

6. Artifact/event/telemetry contract wave
- canonical workspace schema
- typed event payload carriers
- telemetry write facade
- promote existing sanitization into one central policy

### Priority 2: Evolvability And Clean Decomposition

7. RunController dependency cleanup
- `RunControllerConfig`
- adapter creation delegated to registry/factory
- fewer direct concrete imports

8. Gate verdict split
- merge decision vs flow-control signal

9. Shim/package cleanup
- remove `domain/task_contract.py`
- remove `services/adapter_factory.py`
- remove `services/context_assembler.py`
- reorganize `services/` only alongside real ownership changes

## Detailed Execution Mainline

### Tranche A1: SQLite Daemon State

Goal:
- replace `daemon_state.json` and ad-hoc retry/lock files with one durable per-issue daemon state substrate

Includes:
- daemon state table
- retry metadata
- ownership lease timestamps
- singleton daemon lock
- recovery path rewrite

Done when:
- dual-daemon launch is prevented or fenced
- crash recovery resumes from durable issue state
- retry and dead-letter state no longer depend on stray files

### Tranche A2: Canonical Mission Lifecycle

Goal:
- eliminate internal `MissionStatus` vs `MissionPhase` ambiguity

Includes:
- canonical internal phase
- projection for dashboard and Linear
- explicit mapping layer
- transition validation at mutation boundaries

Done when:
- no internal service advances mission using a second authoritative enum
- Linear and dashboard read the same projected truth

### Tranche A3: Orchestrator Split

Goal:
- reduce `RoundOrchestrator` from sink object to coordinator

Includes:
- `WaveDispatcher`
- `RoundVerifier`
- `AcceptancePipeline`
- smaller round state carrier

Done when:
- acceptance changes do not require editing the entire orchestrator
- dispatch and acceptance can be unit-tested independently

### Tranche A4: Poller/Executor Separation

Goal:
- daemon loop keeps polling/triaging while execution is in flight

Includes:
- queue/enqueue seam
- executor worker group
- admission governor consumes real queue state instead of mostly inferred pressure

Done when:
- long builder/worker runs do not stall daemon intake
- hotfix/high-priority work can be admitted while other execution is active

### Tranche B1: Verification Outcome Contract

Goal:
- make skipped verification explicit and non-pass-like

Includes:
- verification outcome enum
- report/model updates
- learning/evolution consumers updated

Done when:
- unconfigured verification can no longer pollute success learning

### Tranche B2: Context Layering Phase 2

Goal:
- stop crude, silent context inflation and truncation

Includes:
- `MemoryReader` and `MemoryWriter`
- file-aware diff allocation
- truncation metadata
- lazy handles for heavy evidence/archive content

Done when:
- context omission is explicit
- runtime context assembly no longer silently drops critical diff slices

### Tranche B3: Workspace Schema And Event Contracts

Goal:
- make artifact and telemetry structure explicit

Includes:
- workspace schema document/source
- typed event payload carriers
- telemetry facade
- centralized path sanitization policy

Done when:
- path/format changes have one canonical source
- publishers and consumers share the same contract language

### Tranche C1: Controller And Adapter Cleanup

Goal:
- make runtime seams more replaceable without global churn

Includes:
- `RunControllerConfig`
- adapter registry
- fewer direct concrete imports in controller/daemon

Done when:
- adding a new adapter no longer requires editing controller internals and multiple `if` chains

### Tranche C2: Gate And Package Cleanup

Goal:
- finish lower-priority architecture hygiene after runtime risks are reduced

Includes:
- split gate verdict semantics
- remove shims
- package reorg only where ownership is now stable

Done when:
- import graph is cleaner
- flow-control and mergeability semantics are distinct

## Bottom Line

The reviews are correct about the remaining bottlenecks.

The highest-value next wave is not a new architecture. It is:

1. durable daemon/runtime state
2. canonical mission lifecycle
3. orchestrator decomposition and poller/executor separation
4. then contract hardening for verification, context, and artifact/event schemas

Everything else should follow those lines rather than compete with them.
