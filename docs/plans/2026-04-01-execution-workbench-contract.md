# Execution Workbench Contract

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** execution

## Goal

Define the canonical contract for the Execution Workbench so operators can see
live work clearly and safely intervene without reading raw logs.

## Operator Questions This Contract Must Answer

- What is running now?
- Which agent owns it?
- Which runtime is it using?
- What phase is it in?
- Is it healthy, stalled, degraded, or blocked?
- What can I do right now?

If the contract cannot answer those six questions, the execution workbench is
not ready.

## First-Class Objects

- `Agent`
- `Runtime`
- `ActiveWork`
- `QueueEntry`
- `ExecutionSession`
- `ExecutionEvent`
- `OperatorIntervention`

## Canonical Read Models

## 1. Agent

Required fields:

- `agent_id`
- `name`
- `role`
- `status`
- `runtime_id`
- `active_workspace_id`
- `last_active_at`
- `recent_subject_refs`

User-facing meaning:

- who this agent is
- what lane it belongs to
- what it is working on now

## 2. Runtime

Required fields:

- `runtime_id`
- `runtime_kind`
- `mode`
- `health`
- `heartbeat_at`
- `usage_summary`
- `activity_summary`
- `degradation_flags`

User-facing meaning:

- where work is running
- whether the runtime is healthy
- whether the runtime is overloaded or degraded

## 3. ActiveWork

Required fields:

- `active_work_id`
- `workspace_id`
- `subject_id`
- `subject_kind`
- `agent_id`
- `runtime_id`
- `phase`
- `health`
- `status_reason`
- `started_at`
- `updated_at`
- `available_actions`

User-facing meaning:

- the live thing that is happening right now

## 4. QueueEntry

Required fields:

- `queue_entry_id`
- `workspace_id`
- `subject_id`
- `queue_name`
- `position`
- `queue_state`
- `claimed_by_agent_id`
- `claimed_at`

User-facing meaning:

- whether work is still waiting
- whether it has been claimed
- where it sits relative to other work

## 5. ExecutionEvent

Required fields:

- `event_id`
- `workspace_id`
- `execution_session_id`
- `event_type`
- `event_summary`
- `event_source`
- `created_at`
- `artifact_refs`

User-facing meaning:

- the recent event trail that explains what just happened

## 6. OperatorIntervention

Required fields:

- `intervention_id`
- `workspace_id`
- `action`
- `requested_by`
- `requested_at`
- `outcome`
- `outcome_reason`
- `audit_refs`

Supported actions:

- `retry`
- `cancel`
- `reassign`
- `takeover`

## Live UI Contract

The UI must display execution state as operator-readable facts, not as raw
internal data.

### Example of acceptable UI phrasing

- `Implementor is running on local runtime`
- `Blocked on browser verification`
- `Heartbeat missed for 3m`
- `Last event: PR review loop requested rerun`
- `Available actions: retry, takeover`

### Example of unacceptable UI phrasing

- showing only raw JSON
- showing only transcript lines
- showing only colored dots with no reason text
- requiring operators to infer “stalled” from inactivity

## Event Trail Contract

Execution Workbench must render a short recent-event trail.

Every event should be understandable in one line.

Examples:

- `Worker claimed packet approval-fix`
- `Browser panel opened login replay`
- `Verification command failed with exit code 1`
- `Runtime entered degraded state due to token exhaustion`

This is mandatory because execution trust depends on quick explanation.

## Intervention Contract

Every visible action must satisfy:

- explicit availability
- explicit preconditions
- auditable outcome
- visible result or failure reason

Operators must never click an action without knowing:

- what it will do
- whether it is allowed
- what happened after it ran

## Browser and Terminal Surface Rule

Execution Workbench should treat browser and terminal state as first-class
execution surfaces, not hidden debug tools.

Minimum expectations:

- browser activity belongs to a workspace and session
- terminal activity belongs to a workspace and session
- both may emit execution events
- both may attach artifacts that later flow into evidence bundles

## Current Codebase → Execution Contract Convergence

### Current execution producers

- `src/spec_orch/services/run_controller.py`
- `src/spec_orch/services/parallel_run_controller.py`
- `src/spec_orch/services/mission_execution_service.py`
- `src/spec_orch/services/daemon.py`
- `src/spec_orch/services/run_artifact_service.py`
- `src/spec_orch/services/artifact_service.py`
- `src/spec_orch/services/workers/in_memory_worker_handle_factory.py`

### Current dashboard consumers

- `src/spec_orch/dashboard/missions.py`
- `src/spec_orch/dashboard/control.py`
- `src/spec_orch/dashboard/app.py`
- `src/spec_orch/dashboard/api.py`

### Required convergence

1. Normalize execution status carriers under shared operator semantics.
2. Expose runtime registry and active work as canonical substrate read models.
3. Move queue, heartbeat, health, and intervention visibility into canonical
   workbench-facing contracts.
4. Make dashboard execution views consumers of those read models.
5. Keep mission detail as a view over `ActiveWork`, not a bespoke execution
   interpreter.

## What To Borrow Aggressively

This work should directly absorb proven execution workbench patterns:

- agent roster as first-class surface
- runtime roster as first-class surface
- live task visibility
- queue visibility
- browser panel visibility
- intervention visibility
- event-trail visibility

These are not optional polish features. They are core operator requirements.

## Done Means

This contract is ready for implementation when:

- every live workspace can expose one canonical `ActiveWork` object
- every active work item can point to one `Agent` and one `Runtime`
- a stalled or degraded state is explicit and user-readable
- interventions are visible, audited, and outcome-bearing
- the execution UI can explain backend activity without requiring raw logs
