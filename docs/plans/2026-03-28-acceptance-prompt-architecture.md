# Acceptance Evaluator Prompt Architecture

## Goal

Define a production-grade prompt system for SpecOrch acceptance evaluation that supports three distinct user intents instead of treating all QA as one generic browser review:

1. **Feature-scoped verification**
2. **Impact-sweep verification**
3. **Exploratory user-perspective acceptance**

The purpose of this document is to prevent the current failure mode where the evaluator inherits too much of the implementation framing and only catches narrow, route-local defects.

## Current Implementation Status

Part of this architecture is now live:

- mode-aware acceptance campaigns
- explicit coverage budgets (`min_primary_routes`, `related_route_budget`, `interaction_budget`)
- per-route interaction plans
- browser evidence traces that record which interaction steps passed or failed

What is still not live:

- broad autonomous exploratory browsing
- multi-step form/input flows beyond the current minimal click-based sweeps
- stronger calibration and filing policy refinement across different evaluator modes

## Why The Current Prompt Is Not Enough

The current acceptance evaluator prompt is intentionally small and structurally safe, but it has two hard limits:

1. It is still anchored by the mission framing and round artifacts.
2. Its browser evidence is only as broad as the configured route list.

This makes it good at catching:

- obvious regressions
- missing artifacts
- console/page errors
- mismatches between claimed completion and visible output

But weak at catching:

- bad information architecture
- misaligned user flows
- design/UX defects outside the explicit route list
- product-level failure where the implementation is “internally coherent” but wrong from the user’s perspective

So the next step is not “make the prompt longer.” The next step is to introduce **mode-specific evaluator profiles** with different instructions, scope rules, evidence budgets, and filing policies.

## Acceptance Modes

### Mode 1: Feature-Scoped Verification

Use when:

- a feature has a clearly defined blast radius
- we know exactly which routes, components, and states should change
- we want the evaluator to stay tightly focused

Evaluator job:

- verify the intended feature works
- verify expected UI states are present
- verify the change did not obviously break the nearby surface

What it should emphasize:

- correctness against explicit acceptance criteria
- exact route/path coverage
- expected vs actual behavior
- concrete reproduction steps

What it should avoid:

- broad product critique
- speculative redesign feedback
- filing unrelated issues outside the feature scope

Recommended examples:

- a new Mission Detail control
- a Transcript filter behavior change
- one Approval Queue interaction

### Mode 2: Impact-Sweep Verification

Use when:

- a feature affects multiple surfaces
- a refactor may cause distributed regressions
- the implementation is likely to have wider UI or workflow impact

Evaluator job:

- verify the target feature
- sweep adjacent routes and downstream surfaces
- look for regressions created by the change

What it should emphasize:

- wider route coverage
- state transitions across related views
- regression hunting
- consistency across linked surfaces

What it should avoid:

- turning into a total exploratory audit
- filing aesthetic-only issues unless they materially affect use

Recommended examples:

- Mission Launcher changes
- lifecycle/approval state changes
- operator shell navigation changes
- acceptance surface / dashboard route changes

### Mode 3: Exploratory User-Perspective Acceptance

Use when:

- we want a true dogfood pass
- we care about user-perceived quality, not just explicit feature correctness
- we want the evaluator to act more like an independent operator or product critic

Evaluator job:

- behave like a first-principles user/operator
- navigate the product using task-oriented reasoning
- identify where the product is confusing, misleading, slow, brittle, or incomplete

What it should emphasize:

- task completion from user perspective
- information architecture
- discoverability of actions
- terminology clarity
- coherence across the journey
- design/craft/functionality

What it should avoid:

- treating implementation notes as ground truth
- overfitting to the mission author’s design intent
- filing low-value nitpicks as blockers

Recommended examples:

- operator console dogfood
- full dashboard walkthrough
- post-merge acceptance for a large UX slice

## Prompt Stack

The prompt system should be hierarchical.

### Layer 1: Stable System Prompt

This stays mostly fixed.

Responsibilities:

- define the evaluator as independent from the builder
- enforce evidence-based judgment
- define required output schema
- forbid “self-congratulatory” interpretations
- require clear uncertainty handling

Core stance:

- do not assume the builder’s explanation is correct
- use browser evidence and artifacts as the source of truth
- when evidence coverage is incomplete, say so explicitly
- distinguish “not tested” from “tested and failed”

### Layer 2: Mode Prompt

This is the most important new layer.

Each acceptance mode gets a different task frame.

The mode prompt should define:

- objective
- scope boundary
- what counts as success
- what counts as a filing-worthy defect
- whether broad critique is allowed

The key change is:

- **feature-scoped** mode is constrained
- **impact-sweep** mode is semi-constrained
- **exploratory** mode is user/task-first

### Layer 3: Campaign Prompt

This is generated from the specific run.

It should include:

- mission title
- target feature or campaign goal
- acceptance criteria
- constraints
- known affected routes
- known related routes
- operator priority
- issue filing policy

Think of this as the evaluator’s per-run charter.

### Layer 4: Evidence Payload

This is the structured JSON body already being passed today, but it should be expanded and normalized.

Evidence should be grouped into:

- mission intent
- round status
- browser evidence
- screenshots
- console/page errors
- supervisor decision
- worker outputs
- review routes
- tested coverage map
- untested coverage map

The evaluator should be able to explicitly say:

- “I reviewed these routes”
- “I did not review these routes”
- “This finding is high-confidence because the browser evidence directly shows it”

### Layer 5: Output Contract

The evaluator output should keep the current structured form, but with stronger semantics:

- `status`: `pass | warn | fail`
- `summary`
- `confidence`
- `coverage`
- `findings`
- `issue_proposals`
- `artifacts`
- `recommended_next_step`

Add explicit coverage fields:

- `tested_routes`
- `untested_expected_routes`
- `coverage_status`: `complete | partial | insufficient`

This is essential so the system can distinguish:

- “the feature passed”
from
- “we only looked at 2 of 8 important surfaces”

## Recommended Prompt Variants

### Feature-Scoped Variant

Key instruction:

> Verify only the declared feature and its immediately adjacent states. Do not broaden into general product critique unless the issue directly blocks the feature’s intended use.

Best for:

- deterministic follow-up checks
- post-fix validation
- targeted regression review

### Impact-Sweep Variant

Key instruction:

> Verify the target feature and sweep the related routes for regressions or state inconsistencies introduced by this change. Focus on high-signal breakage, not speculative redesign.

Best for:

- moderate-to-large refactors
- multi-surface changes
- lifecycle/navigation changes

### Exploratory Variant

Key instruction:

> Act as an independent operator using the product to complete the intended task. Do not assume the mission framing or UI structure is correct. Evaluate whether the system is understandable, discoverable, and effective from the user’s perspective.

Best for:

- true dogfood
- operator-console quality passes
- pre-release acceptance

## Evidence Strategy Per Mode

### Feature-Scoped

- 1-3 primary routes
- 1 adjacent sanity route
- optional selector assertions
- low screenshot budget

### Impact-Sweep

- primary routes
- adjacent routes
- downstream routes touched by state changes
- medium screenshot budget

### Exploratory

- seed routes plus expansion rules
- route graph or tab graph traversal
- task-driven navigation
- larger screenshot budget
- explicit “coverage gaps” reporting

## Filing Policy Per Mode

### Feature-Scoped

Auto-file only when:

- defect is directly in scope
- confidence is high
- repro is clear

### Impact-Sweep

Auto-file when:

- defect is a likely regression from the current change
- severity is medium/high and confidence is strong

### Exploratory

Default to:

- auto-file clear broken flows
- hold “design/UX concern” items for operator review unless very severe

This avoids flooding Linear with opinionated but ambiguous design complaints.

## Architecture Changes Needed

### 1. Acceptance Campaign Model

Add a new acceptance campaign object, conceptually:

- `mode`
- `goal`
- `primary_routes`
- `related_routes`
- `coverage_expectations`
- `filing_policy`
- `exploration_budget`

This should sit above the raw environment-based route list.

### 2. Browser Route Planner

Move from:

- one static env route list

To:

- mode-aware route planning
- optional route expansion
- task-specific route bundles

### 3. Prompt Composer

Create a dedicated prompt composer that assembles:

- stable system prompt
- mode prompt
- campaign prompt
- evidence payload

Do not keep this as one monolithic string constant.

### 4. Coverage Reporter

Add explicit tested/untested coverage tracking so acceptance results are honest about scope.

### 5. Dashboard Surface Update

The Acceptance surface should show:

- which mode ran
- what routes were expected
- what routes were actually tested
- why findings were or were not auto-filed

## Implementation Order

### Slice A: Prompt Architecture

- add acceptance mode enum/config
- add acceptance campaign schema
- add prompt composer
- keep browser collector as-is

### Slice B: Route Planning

- map mode -> route strategy
- support feature-scoped route bundle
- support impact-sweep route bundle
- add exploratory seed route support

### Slice C: Coverage and Filing Policy

- report tested vs expected coverage
- mode-specific filing thresholds
- operator-visible rationale in dashboard

### Slice D: Exploratory Interaction Layer

Only after the above:

- add click/tab/task interaction plans
- support task-driven exploration rather than screenshot-only route fetches

## Immediate Recommendation

The next engineering slice should **not** jump straight to free-form exploratory clicking.

Do this first:

1. add explicit `acceptance_mode`
2. add acceptance campaign schema
3. replace the current single generic evaluator prompt with three mode-specific prompt variants
4. upgrade the Acceptance surface to show coverage

That gives us a controlled system with clear semantics before we add a more agentic browser layer.

## Success Criteria

This prompt architecture is successful when:

- a narrow feature check stays narrow
- a broad regression sweep covers related surfaces without exploding scope
- an exploratory dogfood pass can criticize the product from the operator perspective instead of merely validating the builder’s framing
- acceptance results clearly state what was tested and what was not
- issue filing behavior changes by mode instead of being one global threshold
