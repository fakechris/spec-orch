# Epic 4 Semantic Completion Tranche

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Completed for current program phase; full agentic graph runtime explicitly deferred  

## Goal

Capture the remaining work needed so Epic 4 can move from "semantic baseline
landed" to "design-complete for this program phase".

This tranche exists because the core semantic objects were landed in code, but
the three canonical Epic 4 design references are not yet implemented end to
end:

1. `docs/plans/2026-03-30-acpx-agentic-graphs-epic-4-alignment.md`
2. `docs/plans/2026-03-30-acceptance-routing-policy.md`
3. `docs/plans/2026-03-30-candidate-findings-review-sop.md`

## What Is Already Landed

- `acceptance_core/` exists and is the canonical home for:
  - routing policy objects
  - candidate-finding / observation / workflow-state objects
  - calibration helpers
  - disposition seam into `decision_core`
- Epic 4 and Epic 5 baselines were merged in PR #164.

## What This Tranche Closed

### 1. Routing Policy Tightening

Implemented in bounded form:

- policy-critical knobs now use constrained enum-like types
- `compare_overlay` only activates when compare intent is present **and**
  baseline availability is true
- `workflow_tuning_availability` is now a first-class routing input
- high mutation risk now forces a conservative `recon` fallback with explicit
  routing reason

### 2. Candidate-Finding Governance Completion

Implemented in bounded form:

- observation → candidate promotion now has an explicit helper seam
- candidate findings now preserve governance metadata for:
  - source observation
  - reviewer identity
  - review note
  - dismissal reason
  - supersession link
- disposition helpers can now apply governance metadata directly onto
  candidate findings

### 3. Calibration Harness Hardening

Implemented in bounded form:

- calibration harness now handles missing actual reviews without crashing
- output now surfaces explicit `missing_review` mismatches
- workflow-tuning-oriented drift now includes:
  - graph-profile drift
  - workflow-tuning note drift
  - step-artifact drift

## What Is Intentionally Deferred

### ACPX-Inspired Workflow Runtime

Current state:

- `workflow tuning` and `graph_profile` are now part of the semantic layer
- calibration and provenance can express workflow drift explicitly

Deferred beyond this tranche:

- real graph/runtime activation based on tuned workflow availability
- stepwise prompt reveal / per-step artifact runtime behavior
- explicit graph-level observability beyond stored semantic fields

This is intentionally not part of the current-program semantic completion gate.
It should be treated as later runtime/orchestration work, not as missing Epic 4
semantic closure.

## Completion Criteria

Epic 4 should only be considered semantically complete for this phase when:

- routing policy gaps above are implemented in bounded form
- candidate-finding governance gaps above are implemented in bounded form
- calibration harness safety gaps above are implemented in bounded form
- ACPX-inspired workflow semantics are explicitly reframed as later
  runtime/orchestration work

These criteria are now satisfied for the current program phase.

## Linear Follow-Up Mapping

This tranche should remain visible in Linear even if implementation shifts to
later epics. The minimum follow-up issue set is:

1. `Epic 4 follow-up: tighten routing policy semantics`
2. `Epic 4 follow-up: complete candidate-finding governance seam`
3. `Epic 4 follow-up: harden calibration harness and workflow drift handling`

These issues should remain attached to Epic 4 history or be explicitly replaced
by a later runtime/orchestration epic rather than being silently absorbed.
