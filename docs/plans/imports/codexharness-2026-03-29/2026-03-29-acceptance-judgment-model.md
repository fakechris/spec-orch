# Acceptance Judgment Model v0

> Drafted after `Workflow Replay E2E`, `Fresh Acpx Mission E2E`, `SON-264 Exploratory Acceptance`, and `SON-265 Dashboard Critique Rubric`.

## Goal

Define the runtime judgment model for acceptance so SpecOrch can:

- route new requests without asking users for internal framework concepts
- distinguish execution mode from judgment outcome
- preserve uncertain but valuable UX critique without over-filing bugs
- graduate repeated exploratory findings into reusable calibration assets

This document defines the judgment layer only. It does not define product-specific rubric details or fixture contents.

## Core Principle

Harness absorbs complexity.

Users should provide:

- business goal
- target
- hard constraints

Users should not be asked to provide:

- acceptance submode
- page type
- surface archetype
- critique axis
- disposition state

Those are internal harness concepts and must be inferred or conservatively approximated by the system.

## Four Runtime Axes

Acceptance runtime must be modeled across four orthogonal axes.

### 1. Base Run Mode

The execution strategy for collecting evidence.

- `verify`
  - Use when acceptance criteria are explicit and replayable.
  - Goal: confirm whether the contract is satisfied.
- `replay`
  - Use when the system already has artifacts or prior mission context and needs to prove an existing workflow still holds.
  - Goal: validate established workflow behavior.
- `explore`
  - Use when the goal includes discoverability, continuity, terminology, confidence, or broader user-friction critique.
  - Goal: collect bounded exploratory evidence and synthesize critique.
- `recon`
  - Hidden fallback when the harness cannot confidently activate an existing contract or surface pack.
  - Goal: map the surface, discover candidate paths, gather evidence, and avoid premature strong judgments.

### 2. Calibration Overlay

Whether the run should be compared to a baseline or prior judgment asset.

- `compare = false`
  - Standard run.
- `compare = true`
  - Run with baseline fixture, prior judgment, or prior artifact comparison enabled.

`compare` is an overlay, not a sibling mode.

### 3. Judgment Class

The semantic class of the output.

- `confirmed_issue`
  - Evidence is strong enough to support direct filing, blocking, or explicit failure.
- `candidate_finding`
  - The concern appears valuable and actionable, but is not yet strong enough for direct filing.
- `observation`
  - Evidence is descriptive or suggestive, but not yet suitable for queueing as a tracked finding.

### 4. Workflow State

The lifecycle state after a judgment object is created.

- `queued`
- `reviewed`
- `promoted`
- `dismissed`
- `archived`

`held` should not be a first-class ontology term. It is better represented as a `candidate_finding` in `queued` or `reviewed` state.

## Intake Model

The minimum request contract for acceptance should be:

- `goal`
- `target`
- `constraints`

### Goal

Examples:

- "Check whether the new approval path works."
- "Look at this transcript experience from a user perspective."
- "Run the launcher flow and see if anything feels confusing."

### Target

At least one target must be provided or inferred:

- URL
- environment
- mission id
- round id
- PR / branch / runtime reference
- artifact bundle

### Constraints

Examples:

- bounded budget
- do not mutate prod data
- dashboard only
- focus on operator experience
- compare with previous run

## Harness-Owned Judgments

The harness must own at least these five decisions:

1. `contract synthesis`
   - Determine whether enough route/task/surface structure exists to run verify, replay, or explore.
2. `mode selection`
   - Choose `verify`, `replay`, `explore`, or fallback `recon`.
3. `depth and budget`
   - Set route budget, action budget, evidence budget, and stopping conditions.
4. `surface pack / rubric activation`
   - Load the relevant surface-specific rubric and fixture context when available.
5. `disposition thresholding`
   - Decide whether output becomes `confirmed_issue`, `candidate_finding`, or `observation`.

These should never be delegated to the user by default.

## Automatic Mode Selection

The harness should score each request using four internal variables:

- `contract_strength`
  - How explicit and replayable is the acceptance contract?
- `surface_familiarity`
  - Does the harness already know this surface via routes, fixtures, or prior runs?
- `baseline_availability`
  - Is there a prior run, fixture, or known-good comparison target?
- `judgment_risk`
  - How risky would a wrong judgment be?

### Default Routing Heuristic

- Strong contract + explicit pass/fail criteria -> `verify`
- Existing artifacts + workflow continuity goal -> `replay`
- User-friction / discoverability / continuity / UX signal goal -> `explore`
- Weak contract or unknown surface -> `recon`

## Disposition Rules

### `confirmed_issue`

Use when:

- the failure is reproducible or strongly evidenced
- the concern maps to a clear contract or rubric violation
- the next action is obvious enough to justify filing or blocking

Typical examples:

- route fails to load
- action returns error
- state transition is wrong
- critical evidence is inaccessible in a reproducible way

### `candidate_finding`

Use when:

- the concern is credible and operator-relevant
- there is meaningful evidence
- but the chain from signal -> root problem -> issue is not yet fully closed

Typical examples:

- transcript entry point is not self-evident
- empty state hides retry reason
- terminology creates context-switch friction
- evidence can be reached, but not within expected operator effort

### `observation`

Use when:

- the run discovered descriptive information or weak signals
- but not enough to justify queueing as a tracked finding

Typical examples:

- route structure is more complex than expected
- a flow has many branches but no clear UX problem yet
- a new surface pack may be needed

Observations should not default into the same review queue as candidate findings.

## Candidate Finding Object Model

The minimum object for `candidate_finding` should include:

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

Optional fields may include:

- `critique_axis`
- `operator_task`
- `why_it_matters`
- `related_artifacts`
- `baseline_ref`

### Important Modeling Rule

Do not collapse `confidence` and `impact_if_true` into a single priority field.

Low-confidence / high-impact findings and high-confidence / low-impact findings must remain distinguishable.

## Recon Mode

`recon` exists to avoid forcing premature classification.

When the harness cannot confidently activate a known contract or surface pack, it should:

- map accessible routes or tabs
- identify likely task entry points
- collect interaction evidence
- propose candidate rubric or fixture opportunities
- emit `observation` or low-confidence `candidate_finding`

It should not ask the user to classify the page or choose an internal acceptance mode.

## Relationship Between SON-266 and SON-267

### SON-266

Defines the triage and disposition system:

- candidate finding schema
- review queue
- promotion / dismissal protocol
- dedupe and review metrics

### SON-267

Defines the comparative calibration system:

- surface pack fixtures
- gold judgments
- baseline evidence
- compare runs
- regression tracking

`SON-267` should consume `candidate_finding` outputs from `SON-266`, not replace them.

## Surface Pack Boundary

The judgment system should be generic, but rubric and calibration should be surface-specific.

### Generic Layer

- judgment classes
- workflow states
- evidence bundle schema
- review queue
- promotion protocol
- routing heuristics
- metrics

### Surface Pack Layer

- critique axes
- seed routes
- safe-action budget
- fixture sets
- baseline screenshots / traces
- dogfood scenarios
- gold judgments

The current dashboard work should be treated as `Dashboard Surface Pack v1`, not as a special-case judgment system.

## Graduation Loop

The system should support graduation across layers:

1. `observation`
   - weak signal, knowledge only
2. `candidate_finding`
   - queueable concern
3. `confirmed_issue`
   - actionable failure or strong UX issue
4. `fixture_candidate`
   - repeated pattern worth encoding
5. `regression_asset`
   - stable calibration artifact for comparative runs

The ideal end state of a valuable repeated candidate finding is not only bug filing, but eventual promotion into calibration assets.

## Success Criteria

This judgment model is successful when:

- new requests can be routed without asking users internal framework questions
- the harness can conservatively degrade to `recon` instead of stalling
- exploratory runs stop collapsing into binary file-or-drop behavior
- candidate findings can be reviewed without mixing them with weak observations
- repeated candidate findings can graduate into comparative calibration assets

## Follow-On Documents

This document should be followed by:

1. `Acceptance Routing Policy`
   - intake, mode routing, depth policy, compare overlay, recon fallback
2. `Dashboard Surface Pack v1`
   - critique axes, fixtures, baselines, gold judgments, compare protocol
3. `Candidate Findings Review SOP`
   - review flow, dismissal reasons, promotion rules, fixture graduation

## Current Decision

Adopt the following corrections immediately in future design and implementation discussions:

- stop treating `held` as the primary ontology
- treat `candidate_finding` as the primary uncertain-judgment object
- treat `compare` as an overlay, not a sibling acceptance mode
- add `recon` as a first-class internal fallback
- keep user input minimal: `goal + target + constraints`
