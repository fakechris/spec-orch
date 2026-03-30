# Shared Execution Semantics

> Status: design framing for shared semantic layer
> Date: 2026-03-29
> Scope: semantics only; does not require a single runtime owner

## Purpose

This document captures the recommended shared semantic layer between the current `issue` spine and `Mission` spine.

It is intentionally narrower than a full architecture rewrite.
The goal is to answer:

- what should be shared
- what should stay separate
- how current paths map into the shared semantic vocabulary

## Executive Summary

The recommended approach is:

- **share semantic objects**
- **do not force shared runtime owners**

Specifically:

- `Issue` and `WorkPacket` should enter the same **ExecutionUnit family**
- issue runs, mission leaf sends, and packet executor runs should enter the same **ExecutionAttempt family**
- their results should enter the same **ExecutionOutcome family**
- evidence references should enter the same **ArtifactRef family**

At the same time:

- `Mission` should remain a contract/program object
- `Round` should remain a supervision object
- `RunController` and `RoundOrchestrator` should remain distinct owners unless a later extraction proves otherwise

This is the core rule:

> **shared schema, different closure location**

That means:

- issue path closes at `scope=leaf`
- mission path often closes at `scope=round`

## 1. Non-Goals

This design does **not** do the following:

- unify `Mission` and `Issue` into one object
- unify `RunController` and `RoundOrchestrator` into one owner
- force the same session model everywhere
- normalize all filenames before semantics are stable

## 2. Recommended Shared Semantic Objects

### 2.1 ExecutionUnit

**Purpose:** the smallest object the runtime intends to execute.

Current members of the family:

- `Issue`
- `WorkPacket`

Important rule:

- `Mission` is not an `ExecutionUnit`
- `Round` is not an `ExecutionUnit`

### 2.2 ExecutionAttempt

**Purpose:** one concrete try to execute one `ExecutionUnit` under one owner and one continuity model.

Recommended minimum fields:

- `attempt_id`
- `unit_kind`
- `unit_id`
- `owner_kind`
- `continuity_kind`
- `continuity_id`
- `workspace_root`
- `attempt_state`
- `started_at`
- `completed_at`
- `outcome`

Recommended `attempt_state` values:

- `created`
- `running`
- `completed`
- `cancelled`

Important rule:

- `ExecutionAttempt` is not the same thing as `Run`
- `Run` is an issue-path specialization of `ExecutionAttempt`

### 2.3 ExecutionOutcome

**Purpose:** the normalized result of one `ExecutionAttempt`.

Recommended minimum fields:

- `unit_kind`
- `owner_kind`
- `status`
- `build`
- `verification`
- `review`
- `gate`
- `artifacts`

Recommended `status` values:

- `succeeded`
- `failed`
- `partial`
- `blocked`

Important rule:

- `review` and `gate` are allowed to be null
- mission leaf execution must not be forced to look like a full issue closure

### 2.4 ArtifactRef

**Purpose:** one semantic reference to persisted evidence.

Recommended minimum fields:

- `key`
- `scope`
- `producer_kind`
- `subject_kind`
- `carrier_kind`
- `path`

Recommended `scope` values:

- `leaf`
- `round`

This allows the same semantic key to mature at different closure locations.

### 2.5 SupervisionCycle

**Purpose:** the oversight loop that evaluates one or more `ExecutionAttempt`s and decides the next action.

Current member of the family:

- mission `Round`

Important rule:

- `Round` is not an `ExecutionAttempt`
- `Round` supervises `ExecutionAttempt`s and produces `RoundDecision`

## 3. Mapping Current Paths Into Shared Semantics

### 3.1 issue path

```text
Issue
  -> ExecutionAttempt(owner=run_controller, continuity=file_backed_run)
    -> ExecutionOutcome(scope=leaf, often full)
```

Interpretation:

- `Issue` is the `ExecutionUnit`
- `RunController` owns the `ExecutionAttempt`
- `Run` is the issue-specific name for this attempt family member
- `ExecutionOutcome` is usually fully populated at leaf level

### 3.2 Mission leaf path

```text
WorkPacket
  -> ExecutionAttempt(owner=round_worker, continuity=worker_session|oneshot_worker)
    -> ExecutionOutcome(scope=leaf, sparse)
```

Interpretation:

- `WorkPacket` is the `ExecutionUnit`
- `WorkerHandle.send()` owns the local execution attempt
- leaf outcome is intentionally sparse
- later supervision is expected

### 3.3 run-plan packet path

```text
WorkPacket
  -> ExecutionAttempt(owner=packet_executor, continuity=subprocess_packet)
    -> ExecutionOutcome(scope=leaf, thin or medium)
```

Interpretation:

- `WorkPacket` is still the unit
- `PacketExecutor` owns the attempt
- `FullPipelinePacketExecutor` may populate `verification`
- `review` and `gate` are still often absent or thin

### 3.4 Mission round path

```text
Round
  -> supervises many ExecutionAttempt
  -> aggregates evidence
  -> produces RoundDecision
```

Interpretation:

- round is not the attempt
- round is the current `SupervisionCycle`
- mission closure usually becomes meaningful here

## 4. Recommended Continuity Model

`continuity_kind` should explicitly encode how a path keeps going without collapsing everything into “session”.

Recommended current values:

- `file_backed_run`
- `worker_session`
- `oneshot_worker`
- `subprocess_packet`

Recommended rule:

- `continuity_id` may be null when the path has no stable reusable identity
- `continuity_id` should be present when the path is genuinely resumable or reusable

This keeps `subprocess_packet` from pretending to have the same continuity semantics as a worker session.

## 5. Recommended Artifact Semantics

Recommended first shared semantic keys:

- `builder_report`
- `event_log`
- `manifest`
- `workspace_root`
- `verification_report`
- `review_report`
- `gate_report`
- `acceptance_report`
- `visual_report`
- `browser_evidence`

Current interpretation:

- naturally shared now:
  - `builder_report`
  - `event_log`
  - `workspace_root`
- shared but at different closure layers:
  - `verification_report`
  - `review_report`
  - `gate_report`
  - `acceptance_report`
- mission-native today:
  - `visual_report`
  - `browser_evidence`

## 6. What Should Stay Separate For Now

These boundaries should remain separate unless later evidence strongly supports extraction.

### 6.1 Contract-layer objects

Do not unify:

- `Mission`
- `Issue`

Reason:

- they are not the same semantic object
- one is program/contract scoped
- one is input/run scoped

### 6.2 Runtime owners

Do not unify:

- `RunController`
- `RoundOrchestrator`
- `MissionLifecycleManager`

Reason:

- they close different loops
- they operate at different scopes

### 6.3 Supervision and execution

Do not collapse:

- `ExecutionAttempt`
- `SupervisionCycle`

Reason:

- one is local try
- one is oversight + aggregation + next-step decision

## 7. Minimal Adoption Sequence

This design can be adopted incrementally.

### Phase 1: language convergence

Use the shared semantic vocabulary in architecture docs and reviews:

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- `SupervisionCycle`

### Phase 2: read-side convergence

Teach reporting and inspection layers to read current issue and mission artifacts into the same semantic view.

Examples:

- dashboard detail views
- replay tooling
- analytics
- evidence analyzers

### Phase 3: write-side convergence

Gradually emit normalized `ExecutionOutcome` and `ArtifactRef` payloads from:

- issue runs
- mission leaf workers
- packet executors
- round supervision

### Phase 4: owner extraction

Only after the read/write semantics are stable, evaluate whether shared owner logic should be extracted.

## 8. Decision Summary

The shared semantic layer should converge on:

- common unit family
- common attempt family
- common outcome family
- common evidence reference family

The current runtime should preserve:

- distinct contract objects
- distinct owners
- distinct closure locations

This is the design center:

> **share what the system means, not prematurely how the system is owned**
