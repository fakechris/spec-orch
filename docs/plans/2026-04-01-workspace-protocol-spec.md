# Workspace Protocol Spec

> **Date:** 2026-04-01
> **Status:** draft v0
> **Scope:** shared protocol across execution, judgment, and learning planes

## Goal

Define the canonical operator workspace model for SpecOrch so the product stops
behaving like a collection of unrelated pages and starts behaving like one
coherent workbench.

The workspace protocol exists so every operator-visible surface can answer:

- what piece of work this is
- what is currently executing
- what evidence belongs to it
- what the current judgment is
- what the system has learned from it

## Why This Exists

Today, SpecOrch has:

- mission detail
- approvals
- transcript
- launcher
- acceptance review
- visual QA
- cost views
- memory and evolution internals

But these are still closer to adjacent pages than to one shared operating
context.

The workspace protocol gives all of them one stable parent object.

## Core Principle

The operator interacts with a `Workspace`, not with disconnected pages.

A workspace is the stable container that binds:

- one mission or issue context
- one or more execution sessions
- one current spec / plan state
- one evidence graph
- one current judgment state
- one learning lineage

## Canonical Workspace Model

## 1. Workspace

The top-level operator object.

Required fields:

- `workspace_id`
- `workspace_kind`
- `workspace_title`
- `subject_id`
- `subject_kind`
- `source_system`
- `state_summary`
- `created_at`
- `updated_at`
- `active_execution_session_id`
- `active_judgment_id`
- `learning_timeline_id`

`workspace_kind` examples:

- `mission`
- `issue`
- `review`
- `acceptance_session`

## 2. Subject

The underlying business object the workspace is about.

Examples:

- a mission
- a Linear issue
- a round review
- a PR-related review context

Required fields:

- `subject_id`
- `subject_kind`
- `subject_title`
- `source_ref`
- `owner_ref`

## 3. Execution Session

The live execution container inside a workspace.

Required fields:

- `execution_session_id`
- `run_id`
- `agent_id`
- `runtime_id`
- `phase`
- `health`
- `status_reason`
- `queue_state`
- `last_event_at`
- `available_actions`

## 4. Evidence Bundle

The canonical operator-readable evidence envelope.

Required fields:

- `evidence_bundle_id`
- `workspace_id`
- `origin_run_id`
- `bundle_kind`
- `artifact_refs`
- `route_refs`
- `step_refs`
- `collected_at`

`bundle_kind` examples:

- `workflow_replay`
- `exploratory_acceptance`
- `visual_qa`
- `cost_incident`

## 5. Judgment

The current review state attached to the workspace.

Required fields:

- `judgment_id`
- `workspace_id`
- `base_run_mode`
- `graph_profile`
- `judgment_class`
- `review_state`
- `confidence`
- `impact_if_true`
- `recommended_next_step`

## 6. Learning Lineage

The promoted and historical learning state attached to the workspace.

Required fields:

- `learning_lineage_id`
- `workspace_id`
- `promoted_refs`
- `memory_refs`
- `fixture_refs`
- `policy_refs`
- `evolution_refs`

## User-Visible Contract

The UI should make the workspace legible in ordinary language.

An operator should be able to read the top of a workspace and immediately
understand:

- `What is this about?`
- `What is happening now?`
- `What is the system currently worried about?`
- `What has already been learned from this work?`

### Example user-visible summary

- `Mission "Fix approval timeout" is running on runtime-2 via Verifier`
- `Current phase: exploratory acceptance`
- `Current judgment: candidate finding on transcript empty-state continuity`
- `Learning impact: no promotion yet; compare replay suggested`

## Workspace Panels

Every workspace may expose panels, but those panels are children of the
workspace, not free-floating pages.

Canonical panels:

- `Execution`
- `Evidence`
- `Judgment`
- `Learning`
- `Browser`
- `Terminal`
- `Changes`
- `Timeline`

Not every workspace must surface every panel at all times, but the protocol
must allow them.

## Ownership Rules

### Runtime-owned

The workspace may show runtime truth, but runtime remains the source of:

- execution session state
- task ownership
- queue state
- runtime health
- live progress

### Decision-owned

The workspace may show judgment truth, but decision remains the source of:

- run mode
- judgment class
- compare overlay
- review/disposition state

### Learning-owned

The workspace may show learning truth, but learning remains the source of:

- memory linkage
- fixture graduation
- policy promotion / rollback
- evolution proposal lineage

## Current Codebase → Workspace Protocol Convergence

The current repository does not yet expose `Workspace` as a formal domain
object. It is spread across dashboard and service layers.

### Current file anchors

- subject / mission state:
  - `src/spec_orch/services/mission_service.py`
  - `src/spec_orch/services/mission_execution_service.py`
- execution state:
  - `src/spec_orch/services/run_controller.py`
  - `src/spec_orch/services/parallel_run_controller.py`
  - `src/spec_orch/services/daemon.py`
- judgment state:
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/services/acceptance/`
- learning state:
  - `src/spec_orch/services/memory/`
  - `src/spec_orch/services/evolution/`
- workspace UI shell today:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/api.py`
  - `src/spec_orch/dashboard/missions.py`
  - `src/spec_orch/dashboard/surfaces.py`
  - `src/spec_orch/dashboard/transcript.py`

### Required convergence

1. Add a shared workspace-facing read model in the domain/shared semantics layer.
2. Teach execution, judgment, and learning producers to attach their carriers to
   a `workspace_id`.
3. Move dashboard composition to work from workspace-facing objects rather than
   directly stitching page-specific blobs.
4. Let page routes remain, but make them views over the workspace instead of
   alternate sources of truth.

## Required Non-Goals

This spec does not require:

- a full directory rename immediately
- replacing mission detail in one cut
- deleting legacy routes before the workbench is stable
- forcing all pages into one monolithic frontend component

## Done Means

The workspace protocol is “done enough” for implementation when:

- execution, judgment, and learning carriers can all point to one
  `workspace_id`
- the dashboard can render a coherent workspace header and state summary
- new workbench surfaces can read from canonical workspace-facing contracts
- operators no longer need to manually infer which evidence, review, and
  execution state belong together
