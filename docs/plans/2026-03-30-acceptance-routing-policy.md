# Acceptance Routing Policy

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Issue:** E4-I2 — Define acceptance routing policy  
**Status:** Implemented baseline with tuned graph activation

## Goal

Define how the harness auto-routes new acceptance requests without asking users
for internal framework concepts.

This policy turns the judgment model into runtime behavior.

## Core Principle

Users provide:

- `goal`
- `target`
- `constraints`

The harness owns:

- contract synthesis
- mode selection
- depth and budget
- surface-pack activation
- compare overlay activation
- disposition thresholding

Users should not be asked to choose:

- acceptance submode
- page type
- graph shape
- critique axis
- review lifecycle state

## Routing Output

Every acceptance intake must produce a routing decision with these fields:

- `base_run_mode`
- `compare_overlay`
- `surface_pack`
- `budget_profile`
- `graph_profile`
- `evidence_plan`
- `risk_posture`

Where:

- `base_run_mode` is one of:
  - `verify`
  - `replay`
  - `explore`
  - `recon`
- `compare_overlay` is:
  - `true`
  - `false`

## Intake Contract

### 1. Goal

The user states the business intent in ordinary language.

Examples:

- "Check whether this approval flow still works."
- "Look at this transcript experience from an operator perspective."
- "Run this mission and compare acceptance output with the previous baseline."

### 2. Target

At least one target must be explicit or derivable:

- URL
- environment
- mission id
- round id
- PR / branch / commit
- artifact bundle
- dashboard surface reference

### 3. Constraints

Examples:

- dashboard only
- bounded budget
- no mutating production-like state
- compare with last successful run
- focus on operator discoverability

## Internal Routing Inputs

The harness computes routing using six internal variables:

- `contract_strength`
- `surface_familiarity`
- `baseline_availability`
- `judgment_risk`
- `mutation_risk`
- `workflow_tuning_availability`

### Contract Strength

How explicit and replayable is the acceptance contract?

High examples:

- fixed workflow with step expectations
- known pass/fail assertions
- established selector-backed action plan

Low examples:

- vague "look around this new page"
- unexplored surface with no stable route map

### Surface Familiarity

How much prior structure exists for the target surface?

Signals:

- known routes
- prior runs
- known surface pack
- known critique axes
- known evidence shape

### Baseline Availability

Whether there is a reusable comparison target.

Examples:

- calibration fixture
- prior successful run
- baseline artifact bundle
- gold judgment example

### Judgment Risk

How costly would a wrong judgment be?

High-risk examples:

- auto-filing
- blocking merge or gate
- critical operator workflow

### Mutation Risk

How dangerous would broad action exploration be?

High-risk examples:

- destructive approvals
- write surfaces
- production-like state mutation

### Workflow Tuning Availability

Whether the harness already has a tuned graph profile for this kind of request.

Examples:

- workflow acceptance graph for selector-backed replay
- dashboard exploratory graph with known route seeds and bounded loops

## Base Run Mode Selection

### `verify`

Choose `verify` when:

- contract strength is high
- explicit pass/fail criteria exist
- workflow is expected to be replayable
- the main question is "does the contract hold?"

Typical use:

- step-based acceptance checks
- selector-backed workflow verification

### `replay`

Choose `replay` when:

- prior artifacts already exist
- the main question is whether an established workflow still holds
- continuity against an existing mission/round context matters

Typical use:

- post-run workflow replay
- artifact-backed verification of an existing mission path

### `explore`

Choose `explore` when:

- the goal includes discoverability, continuity, IA, terminology, or confidence
- contract strength is incomplete but the surface is known enough to inspect
- the harness has enough bounded structure to explore safely

Typical use:

- dashboard/operator-console critique
- exploratory UX acceptance with evidence capture

### `recon`

Choose `recon` when:

- contract strength is low
- surface familiarity is weak
- no trusted surface pack is available
- strong judgment would be premature

Typical use:

- new surface with no mature pack
- unclear flow with weak route knowledge
- early-stage investigation before formal exploratory judgment

`recon` is a conservative fallback, not a failure state.

## Compare Overlay Activation

`compare` must remain an overlay, not a sibling mode.

Set `compare_overlay = true` when at least one of these is true:

- a calibration fixture exists for the active surface pack
- a previous accepted run exists and comparison is relevant
- the change touches prompt/evaluator/routing/policy behavior
- the request explicitly asks for regression comparison

Otherwise:

- `compare_overlay = false`

## Surface Pack Activation

The harness should activate a `surface_pack` when:

- the target surface is recognized
- critique axes are known
- a safe-action budget is known
- there is at least minimal route/evidence structure

Examples:

- `dashboard_surface_pack_v1`

If no trusted pack is available:

- route to `recon`
- emit pack-discovery observations instead of strong findings

## Graph Profile Selection

The harness may activate a tuned graph profile as part of routing.

This is where ACPX-style workflow lessons apply.

### Graph profile examples

- `workflow_replay_graph_v1`
- `dashboard_explore_graph_v1`
- `recon_surface_mapping_graph_v1`

Current implemented baseline maps these ideas to explicit runtime profiles:

- `tuned_workflow_replay_graph`
- `tuned_dashboard_compare_graph`
- `tuned_exploratory_graph`
- `tuned_recon_mapping_graph`

Graph profile controls:

- step ordering
- loop placement
- gate placement
- structured intermediate artifacts

Users do not select graph profiles directly.

## Budget Profiles

Every routing decision must attach a budget profile.

### `strict`

Use when:

- mutation risk is high
- judgment risk is high
- the run is mostly contract verification

### `bounded`

Use when:

- surface is known
- exploratory evidence is needed
- graph tuning exists

### `reconservative`

Use when:

- the harness is in `recon`
- the goal is mapping and evidence discovery, not strong judgment

## Evidence Plans

Routing must also decide which evidence bundle to collect.

Possible evidence elements:

- acceptance review
- browser evidence
- interaction trace
- route coverage
- screenshots / visual gallery
- round summary
- prior baseline refs
- step-level graph artifacts

The evidence plan should be minimal but sufficient for later disposition.

## Default Routing Heuristic

### Rule 1

If contract strength is high and pass/fail criteria are explicit:

- route to `verify`

### Rule 2

If prior mission/round artifacts exist and continuity is the main question:

- route to `replay`

### Rule 3

If the user goal is user-friction or operator-perspective critique and the
surface is familiar enough:

- route to `explore`

### Rule 4

If the harness cannot confidently activate a known contract or surface pack:

- route to `recon`

### Rule 5

If a trusted baseline or fixture exists:

- enable `compare_overlay`

## Recon Fallback

`recon` should do four things:

1. map the surface
2. discover candidate routes and safe affordances
3. capture evidence
4. recommend the cheapest next promotion step

`recon` should produce:

- `observation`
- or at most a low-confidence `candidate_finding`

It should not aggressively file issues.

## Disposition Coupling

Routing does not directly choose the final judgment class, but it constrains what
is appropriate later.

Expected default pairings:

- `verify` -> often `confirmed_issue` or clear pass
- `replay` -> often `confirmed_issue` or clear continuity pass
- `explore` -> often `candidate_finding`
- `recon` -> usually `observation`

These are tendencies, not hard locks.

## Workflow Tuning

Routing policy should explicitly recognize `workflow tuning` as a harness-owned
activity.

Meaning:

- prompt tuning changes evaluator or generator instructions
- workflow tuning changes graph shape, loop placement, handoff structure, and
  per-step artifact expectations

Routing may activate a tuned graph when one exists, but should never require the
user to specify graph internals.

## Non-Goals

This policy does not define:

- candidate-finding schema details
- review queue lifecycle details
- dashboard-specific critique axes
- compare harness implementation details

Those belong to adjacent Epic 4 issues.

## Immediate Follow-Ons

This policy should feed:

1. `Candidate Findings Review SOP`
2. `Dashboard Surface Pack v1`
3. `Acceptance Compare Calibration Harness`
