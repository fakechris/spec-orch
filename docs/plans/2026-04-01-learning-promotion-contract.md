# Learning Promotion Contract

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** learning

## Goal

Define how reviewed judgment becomes durable system learning in SpecOrch.

This contract exists to prevent two failures:

1. raw noise being promoted into long-term truth
2. useful reviewed insights disappearing into backend internals

## Core Principle

Only reviewed judgment may become promoted learning.

Nothing should move directly from:

- raw run output
- raw transcript
- raw evidence bundle

into:

- fixture
- memory
- evolution proposal
- policy change

without passing through reviewed judgment state.

## Promotion Sources

Allowed sources:

- `confirmed_issue`
- reviewed `candidate_finding`
- explicitly promoted `observation`

Disallowed sources:

- unreviewed evidence
- unreviewed observations
- raw runtime events

## Canonical Promotion Targets

- `FixtureCandidate`
- `RegressionAsset`
- `MemoryEntryRef`
- `EvolutionProposalRef`
- `PolicyChangeRef`

## Canonical Objects

## 1. PromotedFinding

Required fields:

- `promoted_finding_id`
- `workspace_id`
- `origin_judgment_ref`
- `origin_review_ref`
- `promotion_target`
- `promoted_at`
- `promoted_by`
- `promotion_reason`

## 2. FixtureCandidate

Required fields:

- `fixture_candidate_id`
- `origin_finding_ref`
- `surface_pack_ref`
- `baseline_shape`
- `graduation_state`
- `replay_requirements`

User-facing meaning:

- a finding that is now important enough to preserve as regression knowledge

## 3. MemoryEntryRef

Required fields:

- `memory_ref_id`
- `origin_finding_ref`
- `memory_layer`
- `distillation_summary`
- `created_at`

User-facing meaning:

- the reviewed insight that has now become reusable memory

## 4. EvolutionProposalRef

Required fields:

- `evolution_ref_id`
- `origin_finding_ref`
- `proposal_kind`
- `proposal_summary`
- `review_state`
- `promotion_state`

User-facing meaning:

- the reviewed finding that triggered an evolution suggestion

## 5. PolicyChangeRef

Required fields:

- `policy_change_ref_id`
- `origin_finding_ref`
- `policy_kind`
- `change_summary`
- `promotion_state`
- `rollback_state`

User-facing meaning:

- the reviewed evidence that changed product or runtime policy

## User-Visible Contract

The Learning Workbench must show:

- what repeated patterns exist
- which reviewed findings were promoted
- where they were promoted to
- whether they are still active
- whether they were rolled back or superseded

### Example acceptable UI phrasing

- `This candidate finding was promoted to dashboard fixture candidate`
- `Reviewed finding linked into semantic memory`
- `Flow policy proposal generated from three reviewed approval failures`
- `Policy rollback triggered after compare drift regression`

### Example unacceptable UI phrasing

- hidden backend promotion with no operator trace
- memory or evolution changes with no evidence lineage
- policy changes with no visible origin finding

## Promotion State Machine

Minimum promotion states:

- `proposed`
- `reviewed`
- `promoted`
- `rolled_back`
- `retired`

These states are separate from judgment class and separate from execution state.

## Graduation Rules

## Candidate → Fixture

Promote when:

- the issue recurs
- the pattern is stable enough to replay
- the surface pack can define a baseline expectation

Do not promote when:

- the finding is too vague
- no stable repro or replay target exists
- the concern is still mostly descriptive

## Candidate / Confirmed → Memory

Promote when:

- the finding teaches a reusable operator or system lesson
- that lesson can improve future routing, review, or explanation

## Candidate / Confirmed → Evolution

Promote when:

- the finding suggests a repeatable prompt, policy, or flow improvement
- the change belongs to system behavior rather than one-off bug fixing

## Candidate / Confirmed → Policy

Promote when:

- the reviewed conclusion should change how the system routes, evaluates, or
  escalates future work

## Current Codebase → Learning Promotion Convergence

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

### Required convergence

1. Introduce canonical promotion carriers between reviewed findings and learning
   systems.
2. Make memory linkage and evolution linkage consume reviewed finding refs
   instead of inferring from raw artifacts.
3. Expose promotion and rollback history as operator-facing read models.
4. Keep underlying memory and evolution internals private where appropriate,
   while making lineage explicit.

## What Must Be Legible To Users

The user should be able to understand:

- why the system thinks a pattern is important
- what that pattern changed
- whether it became a fixture, memory, or policy input
- whether it is still trusted

If a user cannot answer those questions from the UI, the Learning Workbench is
still backend-only.

## Done Means

This contract is ready for implementation when:

- every promoted learning object points back to a reviewed finding
- memory, fixture, evolution, and policy surfaces all preserve lineage
- promotion and rollback are visible and auditable
- repeated pattern reporting is tied to review outcomes, not raw noise
