# Judgment Workbench Contract

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** judgment

## Goal

Define the canonical operator contract for reviewing acceptance and exploratory
judgment in SpecOrch.

The Judgment Workbench must make the system’s reasoning legible, not just the
final result.

## Operator Questions This Contract Must Answer

- What did the system evaluate?
- Which evidence did it use?
- Which mode was active?
- Why is the current judgment what it is?
- Is the current concern confirmed, candidate, or observational?
- What evidence is missing to promote or dismiss it?

## Canonical Objects

- `EvidenceBundle`
- `Judgment`
- `JudgmentTimelineEntry`
- `ConfirmedIssue`
- `CandidateFinding`
- `Observation`
- `CompareOverlay`
- `SurfacePack`

## Canonical Read Models

## 1. EvidenceBundle

Required fields:

- `evidence_bundle_id`
- `workspace_id`
- `origin_run_id`
- `bundle_kind`
- `artifact_refs`
- `route_refs`
- `step_refs`
- `evidence_summary`
- `collected_at`

User-facing meaning:

- what evidence exists
- where it came from
- how much of the surface was actually inspected

## 2. Judgment

Required fields:

- `judgment_id`
- `workspace_id`
- `base_run_mode`
- `graph_profile`
- `risk_posture`
- `judgment_class`
- `review_state`
- `confidence`
- `impact_if_true`
- `repro_status`
- `recommended_next_step`

User-facing meaning:

- the current review state of the workspace

## 3. CandidateFinding

Required fields:

- `candidate_finding_id`
- `workspace_id`
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

This inherits the semantic rules already defined in the Candidate Findings
Review SOP.

## 4. CompareOverlay

Required fields:

- `compare_overlay_id`
- `workspace_id`
- `baseline_ref`
- `drift_summary`
- `artifact_drift_refs`
- `judgment_drift_summary`

User-facing meaning:

- how current evidence and judgment differ from a baseline

## 5. SurfacePack

Required fields:

- `surface_pack_id`
- `surface_name`
- `active_axes`
- `known_routes`
- `graph_profiles`
- `baseline_refs`

User-facing meaning:

- what the system thinks this surface is
- which critique axes and baselines are active

## User-Visible Judgment Contract

The UI must not stop at:

- `status: warn`
- a final prose summary
- hidden evaluation metadata

It must explicitly show:

- active mode:
  - `verify`
  - `replay`
  - `explore`
  - `recon`
- what evidence was gathered
- what judgment class was assigned
- why that judgment was assigned
- what next test or review action is recommended

### Example acceptable UI phrasing

- `Explore mode on transcript surface`
- `Evidence bundle includes browser replay, route trace, and packet transcript`
- `Candidate finding: packet selection is not self-evident for first-time operators`
- `Promotion test: rerun packet flow with baseline compare enabled`

### Example unacceptable UI phrasing

- only showing a final acceptance JSON
- showing pass/warn/fail without evidence summary
- mixing observations and candidate findings into one undifferentiated list
- hiding compare drift behind evaluator internals

## Judgment Timeline Contract

The workbench should present a timeline of how the current judgment formed.

Minimum timeline events:

- routing selected
- graph profile activated
- evidence bundle collected
- compare overlay activated or skipped
- judgment class assigned
- review state changed
- promotion or dismissal outcome

This matters because operators need to see the path, not just the verdict.

## Candidate Review Contract

Candidate findings must be reviewable as first-class objects.

The UI must expose:

- claim
- why it matters
- confidence
- impact if true
- repro status
- hold reason
- promotion test
- recommended next step

And a reviewer must be able to produce one of:

- `promoted`
- `dismissed`
- `archived`
- `remain queued`

## Compare Overlay Contract

Compare is an overlay, not a sibling execution mode.

The workbench must make clear:

- whether compare is active
- what baseline was selected
- where current drift appears
- whether drift changed the final judgment

Without that, compare becomes evaluator magic instead of operator-visible review.

## Current Codebase → Judgment Contract Convergence

### Current judgment producers

- `src/spec_orch/services/round_orchestrator.py`
- `src/spec_orch/services/acceptance/browser_evidence.py`
- `src/spec_orch/services/acceptance/prompt_composer.py`
- `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `src/spec_orch/services/acceptance/linear_filing.py`

### Current dashboard consumers

- `src/spec_orch/dashboard/transcript.py`
- `src/spec_orch/dashboard/surfaces.py`
- `src/spec_orch/dashboard/api.py`
- `src/spec_orch/dashboard/app.py`

### Required convergence

1. Promote evidence bundle carriers into canonical substrate outputs.
2. Promote judgment/disposition carriers into canonical substrate outputs.
3. Keep candidate-finding semantics in canonical models, not page code.
4. Turn dashboard judgment surfaces into views over evidence, judgment, compare,
   and candidate review objects.
5. Keep transcript and acceptance review pages as entry points, but stop letting
   them be the only place judgment is understandable.

## What We Must Keep As Our Differentiation

Execution workbench patterns can be borrowed aggressively, but this layer must
remain SpecOrch-native.

We should preserve and strengthen:

- evidence bundle thinking
- candidate finding lifecycle
- compare overlay semantics
- calibration and promotion logic

This is where SpecOrch should remain stronger than generic execution workbenches.

## Done Means

This contract is ready for implementation when:

- every acceptance or exploratory run yields a canonical `Judgment`
- evidence bundle provenance survives into dashboard surfaces
- candidate findings are reviewable as first-class objects
- compare drift is operator-visible
- the UI makes backend judgment understandable without reading raw artifacts
