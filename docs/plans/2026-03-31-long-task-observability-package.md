# Long-Task Observability Package

**Date:** 2026-03-31  
**Program Fit:** Epics 2-4, with operator-facing impact  
**Status:** Recommended subsystem standard

## Goal

Define the minimum complete package for making long-running agent work visible,
inspectable, and governable.

Observability should make it possible to understand:

- what the agent is doing
- whether it is progressing
- whether it is stalled
- whether it is exhausting budget
- where state changed

## Core Position

Long-task observability is not a dashboard polish feature.

It is a runtime safety and operator-trust subsystem.

Partial adoption is risky.

Examples of risky partial adoption:

- adding a progress label without budget state
- adding summaries without step artifacts
- adding artifacts without transition explanations
- adding telemetry without operator-readable summaries

These produce motion, but not understanding.

## Package Boundary

The Long-Task Observability Package owns:

- progress summaries
- step or batch summaries
- budget tracking visibility
- stall and diminishing-returns signals
- runtime event telemetry
- operator-readable run recaps
- graph or step artifact visibility

It does **not** own:

- final acceptance judgment
- candidate review workflow state
- calibration compare semantics

## Required Capabilities

### 1. Budget Visibility

Operators should be able to see:

- current budget posture
- continuation count
- recent token growth
- whether continuation is still justified

This is required for safe long runs.

### 2. Progress Summaries

The runtime should generate short summaries of current progress.

These summaries should be:

- periodic
- concise
- non-authoritative
- derived from current runtime state

Their job is to explain progress, not to replace acceptance review.

### 3. Step-Or Batch-Level Summaries

When work is structured into graph steps or tool batches, the runtime should
emit summaries at that level too.

This gives operators a more meaningful view than raw transcript alone.

### 4. Stall And Diminishing-Returns Signals

The package should expose when the agent appears to be:

- repeating low-yield actions
- consuming budget with little gain
- blocked on the same issue repeatedly
- taking too long without meaningful state change

### 5. Structured Event Trail

Long runs should emit a structured event stream for:

- step start/end
- tool batch start/end
- compaction events
- advisor or review events
- retries
- stop decisions

### 6. Human-Readable Recaps

Operators should have access to concise recaps suitable for:

- dashboards
- handoffs
- return-from-away states
- run inspection after failure

## Adoption Rule

If SpecOrch adds long-task observability, it should adopt the full package.

Do not stop at a single progress line or a final transcript summary.

## Recommended Runtime Shape

Suggested ownership split:

- `runtime_core.observability.budget`
- `runtime_core.observability.progress`
- `runtime_core.observability.events`
- `runtime_core.observability.recap`

Suggested supporting objects:

- `BudgetPosture`
- `ProgressSummary`
- `ToolBatchSummary`
- `RunRecap`
- `RuntimeEvent`
- `StallSignal`

## Relationship To Acceptance Judgment

Observability and judgment must stay separate.

Observability answers:

- what happened
- how far the run got
- whether it appeared productive

Judgment answers:

- whether the outcome is acceptable
- whether a finding is confirmed, candidate, or observational

Confusing these two layers makes both weaker.

## Failure Modes When Adopted Incompletely

### Summaries without event trail

Makes it hard to verify or debug summary claims.

### Event trail without operator recap

Makes the system inspectable only for engineers.

### Budget counters without stall semantics

Makes the runtime look busy when it is actually looping.

### Observability without graph/step visibility

Makes workflow tuning much harder.

## SpecOrch Recommendation

Adopt the Long-Task Observability Package as runtime-core infrastructure and
use it as operator-facing support for Epic 4 graph execution.

Acceptance judgment should consume observability artifacts, not redefine them.

## Success Criteria

The package should be considered complete when:

- long runs expose budget posture and continuation state
- operators can inspect progress summaries and event trails
- stalls and diminishing returns are visible
- step or batch artifacts are operator-readable
- handoff recaps exist without relying on raw transcript review
