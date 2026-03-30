# ACPX Agentic Graphs Alignment With Epic 4

**Date:** 2026-03-30  
**Program:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Research synthesis

## Goal

Capture what ACPX v0.4 `Agentic Workflows` adds to our current understanding of
acceptance judgment, then translate those lessons into the already-rebased Epic
4 structure instead of reviving `SON-266` / `SON-267` as separate planning
tracks.

## Executive Takeaway

ACPX validates the runtime side of our direction:

- some workflows should be explicit prompt graphs, not single mega-prompts
- stepwise prompt revelation beats one-shot priming-heavy instructions
- structured step outputs improve observability and dashboard monitoring
- flow quality improves through workflow tuning, not just prompt tuning

ACPX does **not** replace Epic 4.

It strengthens our confidence in:

- explicit harness-owned flow control
- structured handoffs between reasoning steps
- dashboards built on per-step artifacts

But it does not yet solve the main Epic 4 problem:

- how exploratory evidence becomes trustworthy judgment
- how uncertain findings are triaged
- how findings graduate into reusable calibration assets

## What ACPX Adds To Our Model

### 1. Workflow Tuning Is A First-Class Activity

ACPX makes an important distinction:

- prompt tuning is not enough
- graph structure, loop placement, and gate placement also need tuning

For Epic 4 this means:

- routing policy should not only choose a run mode
- it should also leave room for tuned execution graphs per surface pack
- compare/calibration must evaluate workflow shape as well as evaluator output

### 2. Persistent Session State Matters

The ACPX PR-triage flow treats one ACP session as a real reasoning carrier, not
just an efficiency trick.

Implication for Epic 4:

- replay and explore should preserve step continuity where it helps judgment
- comparative calibration should compare not only final summaries, but also
  structured intermediate artifacts when available

### 3. Observability Must Exist Per Step

ACPX gets leverage from step-level JSON outputs and run-viewer observability.

Implication for Epic 4:

- `candidate_finding` cannot be only a final evaluator blob
- the review object should preserve which step or evidence slice created the
  concern
- compare overlay should be able to say which semantic field drifted, not just
  that the final label changed

## What ACPX Does Not Change

ACPX is strongest on orchestration. Epic 4 is about judgment governance.

Therefore the following remain true:

- `held` should not become ontology again
- `candidate_finding` remains the right semantic object
- `compare` remains an overlay, not a sibling run mode
- dashboard work remains `surface pack v1`, not the whole product model

## Epic 4 Re-Interpretation After ACPX

The seven Epic 4 issues still stand. ACPX mostly sharpens their meaning.

### E4-I1: Define acceptance judgment model

ACPX reinforces:

- base run mode must stay separate from judgment class
- explicit graph steps are compatible with `verify / replay / explore / recon`
- structured step artifacts should be named in the model, not treated as
  incidental logs

Adjustment:

- the judgment model should mention `workflow tuning` as a sanctioned harness
  activity

### E4-I2: Define acceptance routing policy

ACPX reinforces:

- users should provide high-level goal and target, not internal workflow shape
- the harness should decide whether a tuned graph is needed

Adjustment:

- routing policy should explicitly allow `surface pack` activation to select a
  tuned execution graph, not just an evaluator rubric

### E4-I3: Define candidate-finding object model and review SOP

ACPX reinforces:

- structured step outputs are valuable
- review objects should preserve provenance

Adjustment:

- candidate findings should record `origin_step` or equivalent provenance
- review SOP should preserve the cheapest promotion test based on the exact
  graph step where the concern emerged

### E4-I4: Add decision-core-compatible disposition seam

ACPX reinforces:

- graph outcomes and human handoff states should be explicit
- the acceptance system should not hide disposition inside evaluator text

Adjustment:

- disposition seam should support graph-produced intermediate records without
  inventing acceptance-local lifecycle semantics

### E4-I5: Define dashboard surface pack v1

ACPX reinforces:

- flow structure should be surface-aware
- dashboard packs should include route seeds, budgets, and tuned loops

Adjustment:

- `surface pack` should explicitly own:
  - route seeds
  - safe-action budget
  - tuned graph notes
  - expected step artifacts

### E4-I6: Add comparative calibration harness

ACPX reinforces:

- dashboards need visibility into drift at the step level
- final summary comparison alone is not enough

Adjustment:

- compare harness should eventually compare:
  - final judgment
  - semantic fields
  - selected step artifacts
  - graph-level drift signals

### E4-I7: Add candidate-to-fixture graduation loop

ACPX reinforces:

- repeated workflow patterns deserve promotion into stable assets
- tuned graphs should leave behind reusable expectations

Adjustment:

- graduation loop should cover not only final findings, but also recurrent graph
  patterns that repeatedly create high-value candidate findings

## Recommended Vocabulary Update

Epic 4 should add one explicit phrase to its planning language:

- `workflow tuning`

Recommended interpretation:

- prompt tuning adjusts evaluator or generator instructions
- workflow tuning adjusts graph structure, step ordering, loops, gates, and
  structured handoffs

This term fits naturally under Epic 4 without creating a parallel program.

## Recommended Document Impact

This research should update how we write the remaining Epic 4 docs.

### Acceptance Judgment Model

Add:

- step provenance matters
- workflow tuning is a first-class harness activity

### Acceptance Routing Policy

Add:

- routing may activate a tuned graph through the surface pack
- unknown surfaces may route to `recon` before any stronger graph is activated

### Dashboard Surface Pack v1

Add:

- tuned graph notes
- expected structured intermediate artifacts
- known loop and gate points for dashboard acceptance

### Comparative Calibration Harness

Add:

- field drift is necessary but insufficient
- selected step-artifact drift should become comparable over time

## Non-Goals

This note does not recommend:

- replacing Epic 4 with ACPX-style workflow work
- broad runtime rewrites before `runtime_core` and `decision_core` settle
- introducing a second orchestration program next to the 7-epic structure

## Bottom Line

ACPX v0.4 strengthens the front half of our thesis:

- harness-owned graph execution
- explicit step handoffs
- observability through structured artifacts
- workflow tuning as a real engineering discipline

Epic 4 remains necessary because our unsolved problem is later in the chain:

- candidate finding semantics
- disposition and review governance
- comparative calibration
- graduation from exploratory signal to stable regression asset
