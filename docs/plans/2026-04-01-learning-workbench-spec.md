# Learning Workbench Spec

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** learning
> **Depends on:** Workspace Protocol Spec, Learning Promotion Contract

## Goal

Define the operator-facing product surface for how reviewed findings become
durable memory, regression assets, evolution proposals, and policy changes.

The Learning Workbench exists so system learning becomes visible, auditable, and
trustworthy instead of disappearing into backend internals.

## User Problem

Today, SpecOrch already has memory and evolution subsystems, but the operator
cannot easily answer:

- what the system learned recently
- where that learning came from
- whether a repeated problem became a fixture
- which changes were promoted, rolled back, or retired

That makes the system feel powerful but opaque.

## Jobs To Be Done

When I open the learning plane, I want to:

1. see which reviewed findings were promoted
2. understand what they were promoted into
3. understand whether the promotion is still active
4. track repeated patterns across workspaces
5. understand which memory, evolution, or policy changes came from reviewed
   evidence

## Primary Pages and Panels

## 1. Learning Overview

The top-level learning summary.

Shows:

- promoted findings count
- fixture candidate count
- active regression assets
- recent memory-linked findings
- recent evolution proposals
- recent policy promotions and rollbacks

This page should answer:

- what did the system learn lately

## 2. Promotion Timeline

The canonical narrative of reviewed learning.

It should show:

- reviewed finding created
- promoted to fixture candidate
- promoted to memory
- promoted to evolution
- promoted to policy
- rolled back
- retired or superseded

The operator should see learning as a lineage, not as disconnected events.

## 3. Pattern Registry

This surface groups repeated findings and recurring themes.

It should show:

- repeated claim cluster
- surface or route concentration
- linked workspaces
- linked candidate or confirmed findings
- whether the pattern has produced any promoted asset

This page answers:

- what keeps happening
- what we have already done about it

## 4. Fixture and Regression Asset Registry

This is the place where graduated learning becomes durable regression knowledge.

It should show:

- fixture candidate title
- origin finding
- linked surface pack
- baseline shape
- replay requirements
- graduation state
- last replay outcome if available

This is where the operator sees that a repeated reviewed concern has become a
real future guardrail.

## 5. Memory-Linked Findings

This surface shows how reviewed findings became memory.

It should show:

- origin finding
- memory layer
- distillation summary
- freshness
- whether the memory is still active or superseded

The goal is not to show memory internals for their own sake, but to make the
origin and value of memory visible.

## 6. Evolution and Policy Surface

This shows reviewed findings that triggered system change.

It should show:

- evolution proposal kind
- proposal summary
- review state
- promotion state
- linked finding
- linked policy change
- rollback state when relevant

This page is where the operator understands how the system changes itself over
time.

## Information Architecture

Recommended navigation:

1. `Overview`
2. `Promotion Timeline`
3. `Patterns`
4. `Fixtures`
5. `Memory`
6. `Evolution`
7. `Policy`

Recommended top summary row:

- promoted this week
- rolled back this week
- active fixture candidates
- repeated-pattern count
- unresolved promoted candidates

## Required Visible Concepts

The operator must be able to see:

- `promoted`
- `rolled_back`
- `retired`
- `fixture_candidate`
- `regression_asset`
- `memory_linked`
- `evolution_proposal`
- `policy_change`

The workbench should make learning lineage explicit:

- from which reviewed finding
- into which promoted object
- with which outcome

## Required States

### Promotion

- `proposed`
- `reviewed`
- `promoted`
- `rolled_back`
- `retired`

### Fixture Graduation

- `candidate`
- `baseline_defined`
- `replayable`
- `active`
- `retired`

### Policy

- `proposed`
- `active`
- `rolled_back`

Reason text is mandatory.

Examples:

- `promoted: repeated transcript discoverability concern`
- `rolled back: compare drift showed the promoted rule was too aggressive`
- `active fixture: dashboard packet-flow baseline defined`

## User Experience Requirements

Learning Workbench must make learning legible without pretending that every
promotion is final truth.

That means:

- show lineage, not just outcome
- show rollback and retirement, not just promotion
- show repeated pattern context, not isolated memory entries
- show origin finding and workspace context for every promoted object

The operator should feel that learning is governed and reviewable.

## Current Codebase → Learning Workbench Convergence

Learning truth exists in backend services but is not yet a first-class product
surface.

### Current learning producers

- `src/spec_orch/services/memory/service.py`
- `src/spec_orch/services/memory/analytics.py`
- `src/spec_orch/services/memory/distiller.py`
- `src/spec_orch/services/memory/derivation.py`
- `src/spec_orch/services/evolution/evolution_trigger.py`
- `src/spec_orch/services/evolution/prompt_evolver.py`
- `src/spec_orch/services/evolution/intent_evolver.py`
- `src/spec_orch/services/evolution/skill_evolver.py`
- `src/spec_orch/services/evolution/flow_policy_evolver.py`
- `src/spec_orch/services/evolution/gate_policy_evolver.py`

### Current dashboard gap

Current dashboard surfaces do not yet expose:

- promotion lineage
- pattern registry
- fixture registry
- reviewed memory linkage
- evolution and policy histories

### Required convergence

1. introduce canonical promoted-learning read models
2. connect every promoted object to an origin reviewed finding
3. render learning lineage as visible timelines and registries
4. make rollback and retirement visible operator concepts

## What Must Stay SpecOrch-Native

Learning Workbench should remain opinionated about:

- candidate-to-fixture graduation
- memory-linked reviewed findings
- reviewed finding to evolution linkage
- reviewed finding to policy change linkage
- rollback and retirement lineage

These are central to SpecOrch’s differentiation and should not be flattened
into generic analytics.

## Non-Goals

This spec does not define:

- raw runtime event visibility
- execution interventions
- acceptance mode selection
- evidence bundle review semantics

Those belong to the Execution and Judgment workbenches.

## Done Means

Learning Workbench v1 is done when:

1. promoted findings are visible as first-class operator objects
2. pattern registry, fixture registry, memory linkage, and evolution/policy
   history exist as distinct surfaces
3. every promoted object links back to reviewed judgment lineage
4. rollback and retirement are visible, not hidden backend events
5. operators can explain what the system has learned and why that learning is
   still trusted
