# Operator Workbench Program Plan

> **Date:** 2026-04-01
> **Status:** proposed program rebase on top of latest `origin/main`
> **Intent:** converge the next planning wave around three operator-visible
> workbenches while preserving the architecture gains already made in
> `runtime_core`, `decision_core`, `acceptance_core`, memory, and evolution.

## 1. Why Rebase Around Workbenches

SpecOrch already has deep execution, acceptance, memory, and evolution
capabilities, but the product surface is still uneven:

- execution state exists, but it is not yet consistently operator-visible
- judgment exists, but it is still too hidden behind review artifacts and final
  summaries
- learning exists, but it is still mostly a backend plane rather than an
  operator-visible control plane

The right next move is not to add more disconnected pages. It is to reframe the
operator product around three linked workbenches:

1. `Execution Workbench`
2. `Judgment Workbench`
3. `Learning Workbench`

These are product layers, not replacements for `runtime_core` or
`decision_core`. They consume the extracted seams and make them operable.

## 2. Program Principles

- `runtime_core` remains the owner of execution truth
- `decision_core` remains the owner of decision and review truth
- `acceptance_core` remains the owner of acceptance judgment semantics
- workbenches are operator-facing consumers and controllers over those seams
- every workbench must be defined by both a `Spec` and a `Contract`
- every issue must be traceable to one operator question that becomes easier to
  answer

## 3. Workbench A: Execution Workbench v1

### 3.1 Goal

Make execution state first-class and operator-visible so an operator can answer,
without log spelunking:

- what is running now
- who is running it
- where it is running
- what phase it is in
- whether it is healthy, stalled, or degraded
- what intervention is available

### 3.2 Spec

#### Primary operator jobs

- inspect active work without opening raw logs
- see which agent and runtime own a live task
- understand where a run is blocked
- intervene safely by retrying, canceling, reassigning, or taking over

#### First-class objects

- `Agent`
- `Runtime`
- `Queue`
- `Active Work`
- `Execution Session`
- `Execution Event Trail`

#### First-class surfaces

- `Agents`
- `Runtimes`
- `Active Work`
- `Mission / Issue Live Execution Panel`
- `Operator Actions`

#### Non-goals

- redefining execution semantics inside dashboard code
- embedding acceptance judgment logic into execution pages
- replacing existing mission detail or transcript surfaces wholesale in phase 1

### 3.3 Contract

Every live execution subject must expose:

- `subject_id`
- `subject_kind`
- `agent_id`
- `runtime_id`
- `phase`
- `health`
- `status_reason`
- `updated_at`
- `recent_events`
- `available_actions`

Required guarantees:

- active execution state must be reconstructible from canonical runtime seams
- operator actions must write auditable intervention records
- stalled and degraded states must be explicit rather than inferred from silence
- the dashboard must not invent dashboard-only execution truth

### 3.4 Delivery tasks

1. unify execution-facing status carriers and identity fields
2. land runtime health, heartbeat, and usage registry as operator-readable views
3. expose active work inventory and queue views
4. add live execution panels to mission and issue surfaces
5. add auditable operator actions:
   - retry
   - cancel
   - reassign
   - take over
6. add runtime/event timelines and recent-event recaps

## 4. Workbench B: Judgment Workbench v1

### 4.1 Goal

Turn acceptance and evaluation from “result pages” into an operator-visible
judgment system.

An operator should be able to answer:

- what the system evaluated
- what evidence it used
- why it produced the current judgment
- what is confirmed vs provisional vs observational
- what evidence is missing to promote or dismiss a concern

### 4.2 Spec

#### Primary operator jobs

- inspect evidence without reconstructing it manually
- understand current judgment mode and scope
- review candidate findings in context
- compare current judgment to baseline judgment when calibration applies
- decide whether to promote, dismiss, or leave a finding pending

#### First-class objects

- `Evidence Bundle`
- `Judgment`
- `Confirmed Issue`
- `Candidate Finding`
- `Observation`
- `Compare Overlay`
- `Surface Pack`

#### First-class surfaces

- `Evidence Bundle`
- `Judgment Timeline`
- `Candidate Findings Queue`
- `Compare / Calibration View`
- `Surface Pack Inspector`

#### Non-goals

- moving acceptance semantics back into legacy service layers
- reducing exploratory judgment to binary pass/fail
- mixing observation storage with candidate review workflow

### 4.3 Contract

Every acceptance or exploratory run must expose:

- `base_run_mode`
- `graph_profile`
- `risk_posture`
- `evidence_refs`
- `judgment_class`
- `confidence`
- `impact_if_true`
- `repro_status`
- `promotion_test`
- `recommended_next_step`

Required guarantees:

- `confirmed_issue`, `candidate_finding`, and `observation` stay semantically distinct
- provenance must survive from graph step and evidence ref into final review state
- compare is an overlay, not a separate execution mode
- dashboard judgment surfaces remain consumers of `acceptance_core` and `decision_core`

### 4.4 Delivery tasks

1. finalize acceptance judgment model and routing policy as canonical program docs
2. expose evidence bundle inventory and provenance in dashboard
3. expose judgment timeline, rationale, and disposition state
4. expose candidate finding review workflow and promotion tests
5. add compare overlay and baseline drift surfaces
6. land dashboard surface pack v1 as the first calibrated operator surface

## 5. Workbench C: Learning Workbench v1

### 5.1 Goal

Make memory, reviewed findings, fixture graduation, and evolution legible and
operator-visible.

An operator should be able to answer:

- what repeated issues or findings are emerging
- what the system has learned from reviewed outcomes
- which findings became fixtures or policies
- what changed because of those learnings

### 5.2 Spec

#### Primary operator jobs

- inspect learning signals without reading backend files
- see which reviewed findings graduated into fixtures
- see which memory entries or evolution proposals came from reviewed evidence
- audit promotion and rollback of learned policies

#### First-class objects

- `Promoted Finding`
- `Fixture Candidate`
- `Regression Asset`
- `Memory Entry`
- `Evolution Proposal`
- `Policy Change`
- `Learning Timeline`

#### First-class surfaces

- `Learning Timeline`
- `Pattern Registry`
- `Fixture Registry`
- `Evolution Proposal Review`
- `Promotion / Rollback History`

#### Non-goals

- replacing the underlying memory system
- exposing raw implementation internals without review context
- auto-promoting unreviewed evidence directly into policy

### 5.3 Contract

Every reviewed learning object must preserve:

- `origin_type`
- `origin_refs`
- `review_state`
- `promotion_state`
- `rollback_state`
- `memory_refs`
- `fixture_refs`
- `policy_refs`

Required guarantees:

- no high-impact promotion without explicit review state
- reviewed findings can map into memory, fixture, evolution, or dismissal, but
  those exits must be explicit
- promotion and rollback events must be queryable as operator-visible history
- learning surfaces must consume canonical provenance rather than dashboard-only
  annotations

### 5.4 Delivery tasks

1. define learning-plane object model over memory/evolution seams
2. connect reviewed findings into memory ingestion
3. connect repeated reviewed findings into fixture-candidate flow
4. expose regression asset registry and provenance
5. expose learning timeline and repeated-pattern analytics
6. expose evolution proposal and policy promotion history

## 6. Recommended 7-Epic Program Shape

### Epic 1: Shared Operator Semantics

Unify the operator-visible identity, status, event, and artifact vocabulary used
by execution, judgment, and learning surfaces.

### Epic 2: Runtime and Execution Substrate

Strengthen the runtime-side substrate needed by Execution Workbench:
runtime registry, health, heartbeat, queue views, active-work carriers, and
operator intervention seams.

### Epic 3: Decision and Judgment Substrate

Strengthen routing, disposition, review, candidate-finding provenance, and
compare overlay semantics as reusable seams rather than page-specific logic.

### Epic 4: Execution Workbench v1

Build the visible execution workbench over Epics 1-2.

### Epic 5: Judgment Workbench v1

Build the visible judgment workbench over Epics 1-3.

### Epic 6: Learning Workbench v1

Build the visible learning workbench over Epics 1-3 plus existing memory and
evolution systems.

### Epic 7: Surface Cleanup and Cutover

Remove legacy overlap, move read paths to canonical seams, and thin the old
pages once the new workbenches are stable.

## 7. Rollout Order

Recommended order:

1. Epic 1
2. Epic 2
3. Epic 3
4. Epic 4
5. Epic 5
6. Epic 6
7. Epic 7

This keeps the delivery sequence aligned with operator value:

- first make execution visible
- then make judgment explainable
- then make learning inspectable
- only then cut over and clean up

## 8. First Concrete Slice

The first practical slice should be:

1. runtime registry and health carriers
2. active work inventory
3. evidence bundle surface

That sequence immediately combines:

- stronger execution observability
- stronger evidence visibility
- a clean bridge into later judgment and learning work

## 9. Acceptance Of This Program Rebase

This rebase is successful when:

- the next major planning wave is organized around the three workbenches
- every Linear issue clearly belongs to one epic and one operator question
- runtime, judgment, and learning concerns stop leaking into ad hoc surface code
- the dashboard begins to look like one operator control plane rather than a
  collection of result pages
