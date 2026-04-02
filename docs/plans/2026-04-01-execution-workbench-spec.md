# Execution Workbench Spec

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** execution
> **Depends on:** Workspace Protocol Spec, Execution Workbench Contract

## Goal

Define the operator-facing product surface for live execution in SpecOrch.

The Execution Workbench exists so an operator can understand what the system is
doing right now without reading raw transcripts, digging through logs, or
guessing from partial artifacts.

## User Problem

Today, SpecOrch can run meaningful work, but the execution truth is still too
backend-shaped.

An operator often has to infer:

- which agent is active
- which runtime owns the work
- whether progress is healthy or stalled
- whether work is queued or already claimed
- whether a browser or terminal action actually happened

That is acceptable for internal debugging, but not for a durable operator
product.

## Jobs To Be Done

When I open SpecOrch as an operator, I want to:

1. see all currently active work in one place
2. understand who owns each unit of work
3. understand where it is running
4. see why it is progressing, blocked, or degraded
5. intervene safely when necessary

## Primary Pages and Panels

## 1. Active Work

The default execution surface.

Shows:

- active work cards
- queue state
- phase and health
- last event summary
- available interventions

This page should answer:

- what is running now
- what is waiting
- what looks unhealthy

## 2. Agents

Shows agents as first-class operator objects, not as invisible service roles.

Each agent card should show:

- name and role
- current status
- current workspace
- current runtime
- recent activity
- recent outcomes

This page should make it obvious that agents are distinct workers with distinct
lanes, not generic background processes.

## 3. Runtimes

Shows runtime health and load.

Each runtime view should show:

- runtime kind and mode
- health state
- heartbeat freshness
- usage summary
- degradation flags
- active sessions attached to that runtime

This page should answer:

- which runtime is overloaded
- which runtime is unhealthy
- which work is affected by runtime problems

## 4. Workspace Execution Panel

Every workspace detail surface should embed a compact execution panel.

Minimum contents:

- current active work
- owning agent
- runtime
- phase
- health
- last event
- allowed actions

The operator should not have to leave a workspace just to understand whether it
is still moving.

## 5. Browser and Terminal Panels

Browser and terminal are first-class execution surfaces.

They should appear as workspace-linked panels, not as hidden debug tools.

Minimum browser visibility:

- current browser task summary
- recent browser events
- screenshots or snapshots when available
- failures with clear reason text

Minimum terminal visibility:

- current command summary
- recent command outcomes
- failure reasons
- relationship to the active execution session

## Information Architecture

Execution Workbench should be organized around operator questions, not backend
subsystems.

Recommended navigation:

1. `Active Work`
2. `Agents`
3. `Runtimes`
4. workspace-local `Execution`

Recommended global summary row:

- running count
- queued count
- stalled count
- degraded runtime count
- intervention-needed count

## Core UI Objects

Execution Workbench should treat these as stable visible objects:

- `ActiveWork`
- `Agent`
- `Runtime`
- `ExecutionSession`
- `QueueEntry`
- `ExecutionEvent`
- `OperatorIntervention`

Each should have:

- a stable title
- a short state badge
- one-line reason text
- drilldown path

## Required States

Execution UI should use explicit state language.

### Health

- `healthy`
- `stalled`
- `degraded`
- `blocked`

### Queue

- `queued`
- `claimed`
- `running`
- `paused`
- `finished`
- `failed`

### Intervention

- `available`
- `running`
- `succeeded`
- `failed`

The UI must always pair the state label with reason text.

Examples:

- `stalled: no event for 6m`
- `degraded: runtime heartbeat delayed`
- `blocked: waiting for browser verification`

## Operator Actions

Execution Workbench must support:

- `retry`
- `cancel`
- `reassign`
- `takeover`

These actions should only appear when:

- the contract marks them available
- the precondition is satisfied
- the outcome will be auditable

Every action needs:

- button label
- one-line consequence text
- post-action result state

## User Experience Requirements

The operator must be able to understand the system in under 10 seconds from the
top-level execution views.

That means:

- no raw JSON-first screens
- no status-only pills without explanation
- no hidden active work behind multiple clicks
- no browser or terminal behavior buried in logs

The UI should read like a control surface, not like a developer console.

## Current Codebase → Execution Workbench Convergence

Execution truth already exists, but is fragmented.

### Current execution producers

- `src/spec_orch/services/run_controller.py`
- `src/spec_orch/services/parallel_run_controller.py`
- `src/spec_orch/services/mission_execution_service.py`
- `src/spec_orch/services/mission_service.py`
- `src/spec_orch/services/daemon.py`
- `src/spec_orch/services/run_artifact_service.py`
- `src/spec_orch/services/artifact_service.py`
- `src/spec_orch/services/workers/in_memory_worker_handle_factory.py`

### Current dashboard shell surfaces

- `src/spec_orch/dashboard/app.py`
- `src/spec_orch/dashboard/api.py`
- `src/spec_orch/dashboard/shell.py`
- `src/spec_orch/dashboard/control.py`
- `src/spec_orch/dashboard/missions.py`
- `src/spec_orch/dashboard/routes.py`
- `src/spec_orch/dashboard/surfaces.py`

### Required convergence

1. move live execution truth into runtime-owned read models
2. let dashboard consume `ActiveWork`, `Agent`, and `Runtime` objects directly
3. stop rendering execution state indirectly through mission-only pages
4. promote browser and terminal activity into explicit workspace-linked panels

## What To Borrow Aggressively

Execution Workbench should directly absorb mature patterns for:

- agent roster visibility
- runtime roster visibility
- queue and claim visibility
- live task progress visibility
- browser panel visibility
- intervention visibility
- event-trail readability

This is not optional polish. It is the minimum shape of a serious operator
surface.

## Non-Goals

This spec does not define:

- acceptance judgment semantics
- candidate finding review behavior
- fixture graduation
- memory or evolution surfaces

Those belong to the Judgment and Learning workbenches.

## Done Means

Execution Workbench v1 is done when:

1. `Active Work`, `Agents`, and `Runtimes` exist as first-class pages
2. every workspace shows a compact live execution panel
3. browser and terminal activity are visible as workspace-linked execution
   surfaces
4. operators can explain stalled or degraded work without raw log inspection
5. interventions are explicit, auditable, and understandable
