# Acceptance Taxonomy and Epic Structure

## Goal

Define a single product language for SpecOrch acceptance work, and map each acceptance layer to a dedicated epic with a clear goal.

This document exists to stop three different ideas from being mixed together under the same word "acceptance":

- strict verification
- workflow dogfooding
- exploratory user-perspective critique

They are all valid forms of acceptance, but they serve different purposes and should not share the same success criteria or roadmap container.

## Product-Level Definition

In SpecOrch, **acceptance** means:

> evidence-backed judgment about whether the intended user value is real.

That definition stays constant across all layers.

What changes from layer to layer is:

- how broad the scope is
- how much autonomy the evaluator has
- what kind of finding is considered useful
- whether the output is expected to block, guide, or inspire follow-up work

## The Acceptance Stack

### Layer 1: Verification Acceptance

This is the strictest layer.

Purpose:

- verify that a declared feature or change really works
- verify that explicitly in-scope routes and states are covered
- produce stable, repairable findings

Characteristics:

- route-bounded
- contract-aware
- highly repeatable
- suitable for regression gates

What good output looks like:

- exact expected vs actual mismatch
- exact route or component scope
- clear repro steps
- high confidence that a fix can be implemented and re-verified

What it should not do:

- broad product critique
- speculative redesign commentary
- freeform dogfooding beyond defined scope

### Layer 2: Workflow Acceptance

This is the operator-task layer.

Purpose:

- verify that a real user or operator workflow can be completed end-to-end
- verify transitions across multiple surfaces, not just one route
- prove the product is not only visible, but operable

Characteristics:

- flow-bounded rather than page-bounded
- interaction-heavy
- assertion-driven
- still expected to yield repairable findings

What good output looks like:

- clear statement of which step in the workflow failed
- stable automation evidence for that step
- direct linkage to the UI contract or interaction target that needs to change

What it should not do:

- pretend to be broad product critique
- rely on ambiguous selectors or vague “felt broken” observations

### Layer 3: Exploratory Acceptance

This is the user-perspective critique layer.

Purpose:

- dogfood the product from a first-principles user or operator perspective
- identify UX, IA, terminology, and discoverability problems
- challenge implementation framing rather than inherit it

Characteristics:

- less constrained
- broader than one workflow
- allowed to notice product-level discomfort
- lower repeatability than Verification or Workflow Acceptance

What good output looks like:

- coherent critique tied to evidence
- explicit coverage statement
- clear distinction between “I observed a problem” and “I suspect a broader issue”

What it should not do:

- auto-file low-confidence UX commentary as hard bugs
- pretend that partial exploration equals comprehensive verification

### Layer 4: Human Acceptance

This is the final governance layer.

Purpose:

- let human operators confirm, reject, or reinterpret machine findings
- feed those judgments back into evaluator policy and memory

Characteristics:

- human-in-the-loop
- policy-shaping
- not a replacement for machine acceptance
- the place where false positives and false negatives become durable learnings

This layer is not the next thing to implement. It should sit after the first three layers are stable enough to produce consistent evidence.

## Unified Semantics

These terms should stay stable across the product:

- `acceptance`
  - the whole stack
- `verification acceptance`
  - strict, scoped, repair-oriented
- `workflow acceptance`
  - end-to-end task completion
- `exploratory acceptance`
  - user-perspective critique
- `human acceptance`
  - operator judgment and policy correction

Terms to avoid:

- using `QA`, `dogfood`, `review`, and `acceptance` interchangeably
- calling exploratory critique a “regression check”
- calling route-bounded verification a “user-perspective walkthrough”

## Epic Structure

Each acceptance layer should have one dedicated epic with one clear goal.

### Epic A: Verification Acceptance

**Linear:** `SON-242`  
**Goal:** turn acceptance into a stable, route-bounded verifier that produces repairable findings and trustworthy filing behavior.

Current fit:

- `SON-245` route planning and coverage budgets
- `SON-246` interaction-aware browser flows
- `SON-247` adversarial rubric and filing policy
- `SON-248` calibration fixtures and dogfood regression suite

Status:

- functionally complete for the current phase

### Epic B: Workflow Acceptance

**Linear:** new epic required  
**Goal:** prove that real operator workflows can be completed end-to-end with stable interaction semantics, assertions, and actionable failure reports.

Proposed scope:

- stable automation targets for dashboard/workbench interactions
- flow assertions instead of route-only assertions
- operator-task campaigns such as:
  - launch mission
  - switch mission
  - inspect transcript
  - act on approval
  - review visual/cost surfaces
- repair-oriented findings tied to interaction failures

Why separate from `SON-242`:

- this is not just “more routes”
- it changes the unit of acceptance from routes to workflows

### Epic C: Exploratory Acceptance

**Linear:** new epic required  
**Goal:** run bounded but genuinely user-perspective dogfood passes that can expose IA, UX, and discoverability problems without pretending to be strict verification.

Proposed scope:

- task-first exploratory campaigns
- broader route expansion when evidence suggests it
- stronger critique rubric for clarity, discoverability, and operator comprehension
- held findings rather than eager auto-filing for low-confidence UX issues

Why separate from Workflow Acceptance:

- workflow acceptance asks “can the flow complete?”
- exploratory acceptance asks “does this product make sense from the user’s point of view?”

### Epic D: Human Acceptance and Feedback Loop

**Linear:** refocus `SON-244` around this layer  
**Goal:** capture operator judgment on machine findings, convert it into durable learning, and use it to tune policy.

Proposed scope:

- structured operator feedback capture
- feedback synthesis into active learnings
- policy tuning loop for false positives / false negatives

Explicitly deferred from this epic:

- broad social/discussion ingestion

That should not remain bundled with the immediate human-feedback loop.

## Roadmap Decision

The correct implementation order is:

1. Verification Acceptance
2. Workflow Acceptance
3. Exploratory Acceptance
4. Human Acceptance and Feedback Loop

This is the right order because:

- Verification Acceptance gives us stable, repeatable evidence
- Workflow Acceptance turns that evidence into real product-operability checks
- Exploratory Acceptance broadens perspective once the strict loop is already trustworthy
- Human Acceptance should tune mature evaluators, not compensate for immature ones

## What This Means Right Now

The current dashboard dogfood run showed:

- route coverage can be complete
- interaction semantics are still too unstable
- findings are meaningful, but not yet strong enough to close the repair loop

That means the next implementation work should not jump to operator/social feedback yet.

It should first land under **Workflow Acceptance**:

- make core dashboard interactions stable for automation
- make acceptance findings precise and repairable
- rerun the workflow acceptance loop until it can reliably surface actionable bugs

Only after that should we open the human-feedback loop epic.
