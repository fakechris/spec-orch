# Tranche D: Acceptance Core Foundation

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Depends on:** PR #163 merged (`runtime_core` + `decision_core` baseline)  
**Status:** Baseline implemented; semantic rebase landed

## 1. Goal

Establish a minimal `acceptance_core` seam so acceptance judgment stops living
only as a mix of:

- `round_orchestrator` runtime behavior
- evaluator-specific payload parsing
- dashboard surface assumptions
- imported draft docs

This tranche created the first stable object boundary for acceptance judgment,
but the object model now needs a semantic rebase to absorb the 2026-03-30
Epic 4 design updates:

- `docs/plans/2026-03-30-acpx-agentic-graphs-epic-4-alignment.md`
- `docs/plans/2026-03-30-acceptance-routing-policy.md`
- `docs/plans/2026-03-30-candidate-findings-review-sop.md`

The rebase tightens three areas that the baseline only covered minimally:

- richer routing outputs and workflow-tuning activation
- candidate-finding provenance and review discipline
- compare calibration beyond final-label drift

## 2. Scope

This tranche covers only:

1. acceptance-core package skeleton
2. judgment ontology models
3. routing policy models
4. candidate-finding schema and workflow states
5. `decision_core`-compatible disposition bridge

The original baseline did **not** cover:

- dashboard redesign
- fixture graduation automation
- compare harness implementation beyond a thin baseline
- broad `round_orchestrator` runtime rewrite

The semantic rebase extended this tranche to include:

- routing outputs for:
  - `base_run_mode`
  - `budget_profile`
  - `graph_profile`
  - `evidence_plan`
  - `risk_posture`
- candidate-finding provenance fields such as:
  - `baseline_ref`
  - `origin_step`
  - `graph_profile`
  - `run_mode`
  - `compare_overlay`
- compare calibration semantics for:
  - field drift
  - selected step-artifact drift
  - graph-level drift signals

## 3. Target Package Boundary

Add:

- `src/spec_orch/acceptance_core/__init__.py`
- `src/spec_orch/acceptance_core/models.py`
- `src/spec_orch/acceptance_core/routing.py`
- `src/spec_orch/acceptance_core/disposition.py`
- `src/spec_orch/acceptance_core/protocols.py`

Existing services should initially consume these models through wrappers rather
than by moving the whole acceptance runtime at once.

## 4. Task Groups

## 4.1 Task Group D1: Package Skeleton and Canonical Exports

### Purpose

Create the visible home for acceptance judgment primitives.

### Files

- `src/spec_orch/acceptance_core/__init__.py`
- `src/spec_orch/acceptance_core/models.py`
- `src/spec_orch/acceptance_core/routing.py`
- `src/spec_orch/acceptance_core/disposition.py`
- `src/spec_orch/acceptance_core/protocols.py`

### Tests

- `tests/unit/test_acceptance_core_imports.py`

### Acceptance criteria

- package imports cleanly
- exports are explicit
- no service module becomes the canonical type owner for the new primitives

## 4.2 Task Group D2: Judgment Ontology Models

### Purpose

Turn the accepted terminology into real code objects.

### Core objects

- `AcceptanceRunMode`
  - `verify`
  - `replay`
  - `explore`
  - `recon`
- `AcceptanceJudgmentClass`
  - `confirmed_issue`
  - `candidate_finding`
  - `observation`
- `AcceptanceWorkflowState`
  - `queued`
  - `reviewed`
  - `promoted`
  - `dismissed`
  - `archived`
- `CandidateFinding`
- `AcceptanceObservation`
- `AcceptanceJudgment`

### Files

- `src/spec_orch/acceptance_core/models.py`
- wrapper touchpoints:
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/domain/models.py` only if a compatibility adapter is required

### Tests

- `tests/unit/test_acceptance_core_models.py`
- targeted updates:
  - `tests/unit/test_acceptance_models.py`
  - `tests/unit/test_litellm_acceptance_evaluator.py`

### Acceptance criteria

- ontology names from the judgment-model doc are now code-level canonical names
- `held` is not introduced as a first-class enum/state
- evaluator output can be normalized into these canonical classes without
  changing user-facing behavior yet
- candidate-finding objects preserve provenance needed by the new SOP

## 4.3 Task Group D3: Routing Policy Models

### Purpose

Separate acceptance intake/routing policy from ad hoc logic inside
`round_orchestrator`.

### Core objects

- `AcceptanceRequest`
  - `goal`
  - `target`
  - `constraints`
- `AcceptanceRoutingDecision`
  - selected run mode
  - compare overlay flag
  - route budget
  - action budget
  - recon fallback reason
- `AcceptanceSurfacePackRef`

### Files

- `src/spec_orch/acceptance_core/routing.py`
- initial adapter touchpoints:
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/dashboard/launcher.py`

### Tests

- `tests/unit/test_acceptance_core_routing.py`
- targeted updates:
  - `tests/unit/test_dashboard_launcher.py`
  - `tests/unit/test_round_orchestrator.py`

### Acceptance criteria

- routing vocabulary is object-backed instead of only doc-backed
- `compare` is modeled as an overlay, not as a sibling run mode
- `recon` exists as a first-class internal fallback
- routing decisions can encode workflow-tuning activation via `graph_profile`
- routing output supports `budget_profile`, `evidence_plan`, and `risk_posture`

## 4.4 Task Group D4: Candidate-Finding Workflow and Disposition Bridge

### Purpose

Make acceptance review/disposition state compatible with `decision_core`
instead of growing an acceptance-only queue semantics.

### Core objects / helpers

- `AcceptanceDisposition`
- `AcceptanceDispositionDecision`
- mapping from acceptance review outcome -> `DecisionReview` / intervention
  compatible state
- review-state transitions for:
  - `queued`
  - `reviewed`
  - `promoted`
  - `dismissed`
  - `archived`

### Files

- `src/spec_orch/acceptance_core/disposition.py`
- bridge consumers:
  - `src/spec_orch/dashboard/approvals.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/dashboard/surfaces.py`

### Tests

- `tests/unit/test_acceptance_core_disposition.py`
- targeted updates:
  - `tests/unit/test_dashboard_approvals.py`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_round_orchestrator.py`

### Acceptance criteria

- acceptance review/disposition can be expressed without inventing a second
  review queue ontology
- `decision_core` remains the canonical home for generic review/disposition
  carriers
- acceptance-specific classes stay acceptance-specific
- candidate-finding review preserves promotion tests and dedupe-safe provenance

## 5. Recommended Execution Order

1. D1 package skeleton
2. D2 ontology models
3. D3 routing models
4. D4 disposition bridge

Do not parallelize D3 and D4 before D2 is stable.

After the original baseline landed, the semantic rebase order was:

1. D3 routing rebase
2. D2 candidate-finding provenance rebase
3. compare-calibration semantic rebase
4. Epic 5 memory linkage re-alignment against the rebased schema

## 6. Verification Commands

Minimum verification per task group:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_core_imports.py -v
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_core_models.py tests/unit/test_acceptance_models.py tests/unit/test_litellm_acceptance_evaluator.py -v
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_core_routing.py tests/unit/test_dashboard_launcher.py tests/unit/test_round_orchestrator.py -v
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_core_disposition.py tests/unit/test_dashboard_approvals.py tests/unit/test_dashboard_api.py tests/unit/test_round_orchestrator.py -v
uv run --python 3.13 ruff check src/spec_orch/acceptance_core tests/unit/test_acceptance_core_imports.py tests/unit/test_acceptance_core_models.py tests/unit/test_acceptance_core_routing.py tests/unit/test_acceptance_core_disposition.py
```

## 7. PR Cut Recommendation

This tranche should likely land as either:

- one focused PR if the wrappers stay thin

or:

- PR 1: D1 + D2
- PR 2: D3 + D4

Preferred cut:

- merge D1 + D2 first if ontology naming churn appears
- only then land routing/disposition adapters

## 8. Definition of Done

Tranche D is done when:

- `acceptance_core` exists as a visible package
- acceptance judgment terminology is code-level canonical
- routing policy objects exist
- candidate-finding workflow states exist
- disposition semantics bridge cleanly into `decision_core`
- no new durable acceptance-only queue or review truth is introduced in
  `services/`
