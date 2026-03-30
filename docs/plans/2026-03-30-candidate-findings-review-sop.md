# Candidate Findings Review SOP

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Issue:** E4-I3 — Define candidate-finding object model and review SOP  
**Status:** Draft v0

## Goal

Define the minimum review protocol for uncertain but valuable acceptance
judgments so the system can preserve UX and exploratory concerns without
confusing them with confirmed issues or raw observations.

## Core Principle

`candidate_finding` is a judgment class.

It is not:

- a queue name
- a dashboard-only concept
- a synonym for "held"

Workflow state must remain separate from judgment class.

## Judgment Classes In Scope

This SOP assumes the canonical judgment classes are:

- `confirmed_issue`
- `candidate_finding`
- `observation`

Only `candidate_finding` enters this SOP directly.

`observation` may later be promoted into `candidate_finding`, but it should not
share the same default review queue.

## Workflow States

Candidate findings may move through these states:

- `queued`
- `reviewed`
- `promoted`
- `dismissed`
- `archived`

`held` may appear as informal UI wording, but it is not a canonical state or
object type.

## Candidate Finding: Minimum Object Model

Every `candidate_finding` should include:

- `id`
- `claim`
- `surface`
- `route`
- `evidence_refs`
- `confidence`
- `impact_if_true`
- `repro_status`
- `hold_reason`
- `promotion_test`
- `recommended_next_step`
- `dedupe_key`

Recommended additional fields:

- `critique_axis`
- `operator_task`
- `why_it_matters`
- `baseline_ref`
- `origin_step`
- `graph_profile`
- `run_mode`
- `compare_overlay`

## Field Semantics

### `claim`

A concise statement of the concern.

Good:

- `Transcript empty state hides the retry cause`

Bad:

- `The page seems bad`

### `surface`

The high-level subject surface.

Examples:

- `dashboard`
- `transcript`
- `approval_panel`

### `route`

The narrowest stable route or route-like locator available.

Examples:

- `/?mission=<id>&mode=missions&tab=transcript`

### `evidence_refs`

Pointers to concrete supporting artifacts.

Examples:

- `browser_evidence.json`
- screenshot refs
- route coverage refs
- step artifact ids

### `confidence`

How confident the system is that the claim reflects a real problem.

This is not the same as severity.

### `impact_if_true`

How costly or important the issue would be if the claim is valid.

Examples:

- `low`
- `medium`
- `high`

This must remain separate from `confidence`.

### `repro_status`

How repeatable the concern currently is.

Examples:

- `reproduced`
- `suggestive_only`
- `not_retried`

### `hold_reason`

Why the system did not promote this to `confirmed_issue`.

Examples:

- `evidence suggests friction but causality is not closed`
- `operator-visible confusion is credible but not yet reproducible`
- `more targeted replay needed`

### `promotion_test`

The cheapest next action that could validate or refute the finding.

Examples:

- `rerun transcript path with retry artifact visible`
- `compare against known-good transcript empty-state fixture`

### `recommended_next_step`

A human-usable next action.

Examples:

- `review empty-state copy and add retry cause explanation`
- `run targeted compare replay before filing`

### `dedupe_key`

A stable key for grouping repeated findings.

Examples:

- `dashboard:transcript_empty_state_retry_cause`

## Provenance Rule

Every candidate finding should preserve provenance.

At minimum:

- which run created it
- which route or step created it
- which graph profile was active

This matters for:

- dedupe
- promotion
- fixture graduation
- compare drift analysis

## Default Entry Rule

A finding should enter this SOP as `candidate_finding` when:

- the concern is operator-relevant
- the evidence is meaningful
- the claim is more than descriptive
- but direct filing would still be premature

Examples:

- discoverability friction
- unclear terminology
- empty-state continuity gaps
- evidence discoverability gaps

## Non-Entry Rule

Do not create a `candidate_finding` when:

- the signal is purely descriptive
- no route/surface can be named
- there is no actionable next step
- the claim is too weak to distinguish from noise

In those cases, prefer:

- `observation`

## State Transitions

### `queued -> reviewed`

Happens when:

- a human or trusted automated review examines the candidate

### `reviewed -> promoted`

Happens when:

- evidence becomes strong enough for `confirmed_issue`
- or the finding graduates into a fixture candidate with explicit confirmation

### `reviewed -> dismissed`

Happens when:

- review determines the concern is not real
- or the concern is too weak to justify continued tracking

### `reviewed -> archived`

Happens when:

- the concern is no longer active
- or it is retained only for historical reference

### `queued/reviewed -> archived`

Allowed when:

- the finding is superseded by a stronger finding
- or the surface pack changed enough that the old concern is no longer relevant

## Promotion Rules

Promote a `candidate_finding` when one of these becomes true:

1. the claim becomes reproducible
2. comparison against baseline confirms semantic drift
3. repeated runs produce the same concern with stable provenance
4. human review confirms operator impact and desired remediation

Promotion targets may include:

- `confirmed_issue`
- `fixture_candidate`

These are different outcomes and should not be collapsed.

## Dismissal Rules

Dismiss when:

- the claim cannot be reproduced after the promotion test
- a better explanation invalidates the claim
- the signal came from instrumentation noise or misread evidence

Dismissal should preserve:

- dismissal reason
- reviewer identity or review source
- link to superseding finding if relevant

## Observation Promotion Rules

An `observation` may become a `candidate_finding` when:

- a concrete claim can be stated
- a route/surface can be named
- a promotion test can be defined
- the concern now appears operator-relevant

This is the only recommended bridge from observation into the candidate queue.

## Compare Overlay Interaction

When `compare_overlay = true`, review should ask:

- did this candidate appear because current output drifted from a known baseline?
- is the mismatch semantic or superficial?
- does the mismatch strengthen the promotion case?

Compare should influence review confidence, but should not auto-promote by
itself without enough semantic support.

## Relationship To Surface Packs

Surface packs should supply:

- critique axes
- route seeds
- expected evidence shape
- known baseline refs
- graph profile hints

The candidate-finding object remains global.

This prevents dashboard-specific review logic from becoming the ontology.

## Relationship To Workflow Tuning

Candidate findings are not only review outputs. They are also tuning signals.

A strong recurring candidate finding may imply:

- evaluator weakness
- graph ordering weakness
- missing loop/gate
- missing surface-pack guidance
- baseline gap

Therefore candidate review should produce not only:

- issue promotion decisions

but also:

- tuning hints
- fixture-candidate suggestions

## Review Cadence

Minimum cadence for a healthy system:

- review new queued candidates regularly
- dedupe before promotion
- prefer cheap promotion tests before broad reruns

The exact human workflow can vary, but the object model and transitions should
stay stable.

## Non-Goals

This SOP does not define:

- dashboard UI
- decision-core implementation details
- compare harness internals
- memory persistence semantics

Those belong to neighboring Epic 4 issues.

## Immediate Follow-Ons

This SOP should feed:

1. `decision-core-compatible disposition seam`
2. `dashboard surface pack v1`
3. `acceptance compare calibration harness`
4. `candidate-to-fixture graduation loop`
