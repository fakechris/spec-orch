# Canonical Issue and Acceptance Schema

> **Date:** 2026-04-01
> **Status:** draft v0
> **Purpose:** define the durable schema that all conversational entry points
> must normalize into before execution begins

## Goal

Create one stable issue schema that can be produced from:

- Linear-native conversation
- Dashboard-native authoring
- external LLM / scheduler input

This schema should be rich enough for:

- planning
- execution
- acceptance
- later judgment review

without being so backend-shaped that humans cannot read it.

## Relationship to the 7-Epic Program

Primary epic connections:

- `SON-370` Shared Operator Semantics
- `SON-379` Decision and Judgment Substrate
- `SON-390` Judgment Workbench v1

Secondary use:

- `SON-384` consumes issue shape for execution
- `SON-396` consumes reviewed outputs derived from it

## Canonical Issue Schema

### Required fields

- `issue_id`
- `title`
- `problem`
- `goal`
- `constraints`
- `acceptance`
- `evidence_expectations`
- `open_questions`
- `current_plan_hint`
- `origin`
- `source_refs`

### Acceptance Schema

Acceptance should not be a flat bullet dump.

It should contain:

- `success_conditions`
- `failure_conditions`
- `verification_expectations`
- `human_judgment_required`
- `priority_routes_or_surfaces`

### Example shape

```yaml
issue:
  issue_id: SON-000
  title: Fix approval timeout confusion
  problem: >
    Operators cannot tell whether approval submission failed or is still
    pending when the backend stalls.
  goal: >
    Make approval timeout state legible and actionable.
  constraints:
    - Do not change approval backend semantics in this slice.
  acceptance:
    success_conditions:
      - Timeout state is visibly distinct from pending.
      - Operator sees the next valid action.
    failure_conditions:
      - Timeout still looks identical to pending.
    verification_expectations:
      - Workflow replay covers timeout path.
      - Acceptance review checks state terminology and actionability.
    human_judgment_required:
      - UX clarity of the timeout explanation.
    priority_routes_or_surfaces:
      - approvals
      - mission detail
  evidence_expectations:
    - browser evidence
    - transcript evidence
  open_questions:
    - Should timeout be retry-only or allow takeover?
```

## Authoring Rules

### Human-readable first

The schema must remain readable inside Linear and the Dashboard.

### Stable enough for machines

The schema must be deterministic enough that:

- planner
- scoper
- evaluator

can consume it without ambiguous reinterpretation.

### Acceptance must separate objective and subjective checks

The schema must make explicit:

- what can be verified mechanically
- what still needs human/judgment evaluation

## Current Codebase → Future Ownership

Current partial owners:

- [domain/models.py](/Users/chris/.superset/worktrees/spec-orch/codexharness/src/spec_orch/domain/models.py)
- [spec_snapshot_service.py](/Users/chris/.superset/worktrees/spec-orch/codexharness/src/spec_orch/services/spec_snapshot_service.py)
- [domain/protocols.py](/Users/chris/.superset/worktrees/spec-orch/codexharness/src/spec_orch/domain/protocols.py)

Recommended future ownership:

- canonical issue schema should live in `domain/models` or a dedicated
  `domain/intake_models` area
- spec snapshots should consume the canonical issue, not redefine it

## Debugging Model

If issue normalization goes wrong, inspect:

1. source request
2. canonical issue payload
3. acceptance section
4. open question list
5. planner/scoper consumption of the same schema

Common failures:

- issue schema is too vague for planning
- acceptance is too implementation-specific for users
- human and machine views of the issue drift apart

## Done Criteria

This schema is done when:

- all supported entry points normalize into the same structure
- the structure is readable in UI
- planning and evaluation can consume it directly
- acceptance is no longer an ad hoc prose section
