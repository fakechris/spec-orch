# Epic 4 Semantic Completion Tranche

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Open follow-up tranche after PR #164  

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

## What Is Still Incomplete

### 1. Routing Policy Tightening

Current state:

- `AcceptanceRoutingInputs` and `AcceptanceRoutingDecision` exist
- routing emits `base_run_mode`, `budget_profile`, `graph_profile`,
  `evidence_plan`, and `risk_posture`

Still missing:

- constrained types for policy-critical knobs
- stricter `compare_overlay` activation logic
- stronger runtime expression of workflow-tuning availability
- clearer enforcement of `recon` as conservative fallback policy

### 2. Candidate-Finding Governance Completion

Current state:

- `candidate_finding` is a judgment class
- canonical workflow states exist
- provenance fields such as `finding_id`, `baseline_ref`, `origin_step`,
  `graph_profile`, `run_mode`, and `compare_overlay` exist

Still missing:

- doc/code canonicalization around `finding_id`
- explicit observation → candidate promotion seam
- richer dismissal / supersession / reviewer-governance metadata
- stronger review/progression helpers beyond minimum object storage

### 3. Calibration Harness Hardening

Current state:

- compare calibration supports final status drift, field drift, step-artifact
  drift, and graph-profile drift

Still missing:

- graceful handling for missing fixture reviews in harness execution
- clearer fixture/step expectations as runtime-safe output rather than implicit
  assumptions
- stronger workflow-tuning-oriented drift interpretation

### 4. ACPX-Inspired Workflow Semantics

Current state:

- `workflow tuning` and `graph_profile` are part of the semantic layer

Still missing:

- real graph/runtime activation based on tuned workflow availability
- stepwise prompt reveal / per-step artifact runtime behavior
- explicit graph-level observability beyond stored semantic fields

This is intentionally not a new orchestration epic. It remains Epic 4 follow-up.

## Completion Criteria

Epic 4 should only be considered semantically complete for this phase when:

- routing policy gaps above are either implemented or explicitly deferred into a
  later named tranche
- candidate-finding governance gaps above are either implemented or explicitly
  deferred into a later named tranche
- calibration harness safety gaps above are either implemented or explicitly
  deferred into a later named tranche
- ACPX-inspired workflow semantics are either implemented in bounded form or
  explicitly reframed as post-Epic-6 work

## Linear Follow-Up Mapping

This tranche should remain visible in Linear even if implementation shifts to
Epic 6 next. The minimum follow-up issue set is:

1. `Epic 4 follow-up: tighten routing policy semantics`
2. `Epic 4 follow-up: complete candidate-finding governance seam`
3. `Epic 4 follow-up: harden calibration harness and workflow drift handling`

These issues should stay attached to Epic 4 rather than being silently absorbed
into Epic 6.
