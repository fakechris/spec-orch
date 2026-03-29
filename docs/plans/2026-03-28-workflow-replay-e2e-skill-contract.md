# Workflow Replay E2E Skill Contract

## Goal

Fix the method, not just the current dashboard run.

`Workflow Replay E2E` should become a repeatable harness pattern that can be:

- rerun against the same product surface after fixes
- moved to a different dashboard or product surface with a new campaign file
- evaluated by different model providers without changing the browser runner
- turned into a future skill without relying on operator memory

This document defines the execution contract, artifact contract, debugging loop, and portability boundaries for that harness.

Repo-local scaffold manifest:

- `.spec_orch/skills/workflow-replay-e2e.yaml`

## Definitions

### Workflow Replay E2E

Replay a live UI workflow against an already-existing mission, round, or artifact set.

Characteristics:

- drives a real browser against a live app surface
- uses real operator routes, selectors, and action endpoints
- may mutate UI-backed state
- does **not** require a brand-new builder run

### Fresh Acpx Mission E2E

Execute a brand-new mission end-to-end:

- create mission
- approve / plan
- bind Linear if required
- launch
- daemon pickup
- new ACPX builder execution
- post-run dashboard acceptance

`Workflow Replay E2E` proves operability of the control plane.
`Fresh Acpx Mission E2E` proves freshness of the whole delivery pipeline.

## Why This Exists

The dashboard workflow replay already found and closed real issues:

- unstable text-only selectors
- broken inline `onclick` quoting
- missing review-route consumption from inbox items
- dropped packet deep-link state
- approval actions blocked by lifecycle preconditions
- approval-state UI drift after successful actions
- helper bundle export gaps

Those were not model hallucinations. They were real system defects found through repeatable browser evidence.

The method needs to be frozen so future runs do not depend on:

- one operator remembering which routes matter
- one model family behaving the same way forever
- one dashboard surface having the same semantics forever

## Core Principle

`Workflow Replay E2E` is **contract-first**, not model-first.

The stable parts are:

1. surface semantics
2. campaign schema
3. browser evidence schema
4. evaluator output schema
5. repair loop

The model is replaceable only because the protocol around it is stable.

## The Six Layers

### 1. Mission Layer

This defines what is being tested.

Required fields:

- replay type
  - `workflow_replay`
  - `fresh_acpx_mission`
- target mission id
- target round id if relevant
- app base URL
- goal statement
- explicit non-goals

This prevents a replay from being over-claimed as a full pipeline proof.

### 2. Surface Contract Layer

This defines what the browser is allowed to rely on.

The browser runner should prefer stable automation semantics over visible text.

Examples already in use:

- `data-automation-target="mission-card"`
- `data-automation-target="mission-tab"`
- `data-automation-target="approval-action"`
- `data-automation-target="launcher-action"`
- `data-automation-target="launcher-field"`
- `data-automation-target="transcript-filter"`
- `data-automation-target="transcript-inspector"`
- `data-automation-target="internal-route"`
- `data-automation-target="inbox-item"`

Rules:

- every critical interaction should have a stable target
- every critical state transition should have a stable assertion target
- visible text may help humans, but replay should not depend on ambiguous labels

### 3. Campaign Layer

This defines how the replay walks the product.

Campaign responsibilities:

- enumerate routes
- attach interaction plans per route
- define assertions
- define coverage budget
- define success criteria

A campaign is the portable unit. The same harness can be reused on a different app if the campaign and surface contract are updated.

### 4. Browser Runner Layer

This should stay as deterministic as possible.

Responsibilities:

- launch browser
- navigate to route
- execute interactions
- wait for selectors
- capture screenshots
- collect console errors and page errors
- record interaction log
- emit `browser_evidence.json`

This layer should be model-agnostic.

### 5. Evaluator Layer

This is where a model interprets evidence.

Inputs:

- mission goal
- acceptance mode
- campaign
- browser evidence
- round artifacts
- filing policy

Outputs:

- `status`
- `coverage_status`
- `summary`
- `findings`
- `issue_proposals`
- `tested_routes`
- `untested_expected_routes`

This layer is provider-swappable only if the schema is stable.

### 6. Repair Loop Layer

This is the point of the harness.

The loop is:

1. run replay
2. collect evidence
3. isolate concrete failure
4. fix root cause
5. rerun replay
6. confirm the failure disappears

If the loop does not end in a replay-backed confirmation, the harness has not yet produced trustworthy value.

## Workflow Replay E2E Runbook

This is the step-by-step operator flow that a future skill should follow.

### Step 1: Define the replay boundary

Write down:

- what surface is under test
- what kind of replay this is
- what it proves
- what it does not prove

Example:

- proves dashboard operator workflow operability
- does not prove fresh builder execution

### Step 2: Inventory the surface contract

Before replay:

- identify all required stable selectors
- identify all required assertion selectors
- list missing automation semantics

If key controls still depend on repeated visible text, replay is not ready.

### Step 3: Build or update the campaign

For each route:

- route URL
- interaction sequence
- expected terminal state
- evidence that must be captured

Each interaction should be explicit:

- `click_selector`
- `fill_selector`
- `wait_for_selector`

### Step 4: Verify preconditions

Before calling browser replay, confirm:

- target mission exists
- required round artifacts exist
- lifecycle state allows the intended action
- any supporting smoke data exists
- app server is actually serving the intended code

Many replay failures are precondition failures, not product bugs.

### Step 5: Run browser replay

Output should include:

- tested routes
- interaction log
- page errors
- console errors
- screenshot map
- artifact directories

This is the source of truth for whether the replay really happened.

### Step 6: Evaluate findings conservatively

A failure is useful only if it is backed by:

- a concrete selector failure
- a real HTTP failure
- a real page error
- a real mismatch between expected and actual route/state

Low-signal or empty-shell findings should be normalized or dropped.

### Step 7: Debug root cause before fixing

Use the replay evidence to identify:

- is this a real UI bug
- a selector contract bug
- a campaign bug
- a precondition bug
- a local smoke-data bug

Do not patch blindly.

### Step 8: Fix the smallest root cause

Typical fix types:

- add missing automation target
- correct state transition rendering
- preserve route or packet state across refresh
- fix helper export / event handler bug
- align campaign selector with actual rendered state

### Step 9: Rerun the same replay

Do not claim a fix is complete until:

- the same replay passes
- the original failure disappears
- no new page/console errors appear

## Skill-Level Contract

If this becomes a reusable skill, the skill should accept at least:

### Inputs

- `target_url`
- `replay_type`
- `campaign_file`
- `mission_id`
- `round_id`
- `artifact_dir`
- `acceptance_mode`
- `filing_policy`
- optional `provider`
- optional `provider_config`

### Required artifacts

- `browser_evidence.json`
- `acceptance_review.json`
- screenshots or visual output directory
- human-readable summary

### Required success reporting

The skill must report:

- which routes were tested
- which interactions passed
- which interactions failed
- what remains unproven
- whether the run proves `Workflow Replay E2E` only, or also `Fresh Acpx Mission E2E`

## Provider Portability

To support MiniMax or another model, keep these stable:

### Must stay provider-agnostic

- campaign schema
- route plan
- interaction plan
- browser runner behavior
- evidence schema
- acceptance result schema

### Can be provider-specific

- evaluator adapter
- evaluator system prompt tuning
- output parsing quirks
- provider auth/config resolution

This means MiniMax should plug into the evaluator layer, not replace the browser harness.

## Prompt / Skill Guidance Requirements

If implemented as a skill, the skill must explicitly instruct the agent to:

1. distinguish replay type before running anything
2. verify surface contract before trusting selectors
3. check preconditions before treating failures as product bugs
4. prefer selector-based interactions over text-only interactions
5. treat page/console errors as evidence, not noise
6. avoid claiming full E2E freshness from replay-only evidence
7. rerun the same campaign after fixes

The skill should also include a short anti-rationalization section:

- `about:blank` is browser startup noise, not the tested page
- a 409 may be a lifecycle precondition problem, not a UI bug
- a selector timeout may mean stale client state, not failed backend mutation
- a passing API call does not prove the UI rerendered the final state

## Common Failure Modes Seen So Far

These are now known replay pitfalls and should become part of the skill guidance.

### 1. Browser startup noise mistaken for target page

Symptom:

- Playwright logs `about:blank`

Reality:

- this is often just browser startup or session attach
- verify the actual `tested_routes` in browser evidence

### 2. Text selectors collide with repeated UI labels

Symptom:

- strict-mode collision on `Transcript`, `Approve`, or mission title text

Fix:

- add stable automation target

### 3. Inline JS quoting breaks helper buttons

Symptom:

- `Unexpected end of input`

Fix:

- normalize quoting and escape boundaries in inline handlers

### 4. Review routes not consumed

Symptom:

- inbox item opens mission, but not the intended tab or review surface

Fix:

- route-aware inbox handling instead of mission-only selection

### 5. Packet deep-link gets dropped on mission detail load

Symptom:

- route says transcript packet X, but inspector never appears

Fix:

- preserve pending route packet during mission-detail hydration

### 6. Approval action fails because lifecycle preconditions are missing

Symptom:

- action endpoint returns 409

Fix:

- validate active issue / lifecycle state before treating this as a UI defect

### 7. Action succeeds but UI stays in transient state

Symptom:

- backend applies action
- page never settles on final status

Fix:

- rerender after clearing transient local override state

### 8. Helper bundle exports drift from app usage

Symptom:

- route buttons exist conceptually but action link never works

Fix:

- verify helper exports match call sites

## Completion Criteria

`Workflow Replay E2E` for a given surface should only be considered complete when:

1. the surface contract is explicit
2. the campaign is versioned and rerunnable
3. replay produces stable evidence artifacts
4. findings are evidence-backed and actionable
5. at least one real detect -> fix -> replay loop has been completed
6. the current proven scope is documented separately from unproven scope

## Current Dashboard Status

As of the latest dashboard quality pass:

- `Workflow Replay E2E` is proven for the currently scoped dashboard workflow capability inventory
- `Fresh Acpx Mission E2E` is still unproven

That distinction must remain explicit in all future skills and reports.

## Recommended Next Step

Turn this document into a dedicated reusable skill only after:

- the current dashboard workflow replay branch is stabilized for PR
- the final artifact schema is frozen
- one first `Fresh Acpx Mission E2E` path is defined, even if not yet passing

The skill should then become the standardized harness entry point for future product surfaces, not just this dashboard.
