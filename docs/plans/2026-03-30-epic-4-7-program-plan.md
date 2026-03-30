# Epic 4-7 Program Plan After Epic 2-3 Merge

**Date:** 2026-03-30  
**Status:** Epic 4 semantic baseline landed but completion tranche remains; Epic 5 baseline aligned; Epic 6 baseline landed; Epic 7 pending  
**Prerequisite baseline:** PR #163 merged (`runtime_core` + `decision_core` extraction complete for Epics 2-3)

## 1. Purpose

This document rebases the second half of the architecture program after the
merge of Epic 2 and Epic 3.

The old Epic tree remains directionally correct, but it was written before the
repo had:

- a real `runtime_core/`
- a real `decision_core/`
- normalized execution read/write seams
- file-backed `DecisionRecord` / `DecisionReview` / intervention queue

Epic 4-7 should now be planned against the code that actually exists, not the
pre-extraction assumptions.

## 2. Current Baseline

The repo now has three meaningful shared seams:

### 2.1 Execution seam

- `src/spec_orch/domain/execution_semantics.py`
- `src/spec_orch/runtime_core/models.py`
- `src/spec_orch/runtime_core/readers.py`
- `src/spec_orch/runtime_core/writers.py`
- `src/spec_orch/runtime_core/adapters.py`

This is the canonical home for:

- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- normalized execution carriers

### 2.2 Decision seam

- `src/spec_orch/decision_core/models.py`
- `src/spec_orch/decision_core/inventory.py`
- `src/spec_orch/decision_core/records.py`
- `src/spec_orch/decision_core/review_queue.py`
- `src/spec_orch/decision_core/interventions.py`

This is the canonical home for:

- `DecisionPoint`
- `DecisionRecord`
- `DecisionReview`
- `Intervention`
- decision review / response history

### 2.3 Surface compatibility still exists

Legacy service and dashboard surfaces still exist and still work, but they are
now expected to consume the extracted seams rather than define new truth.

That means Epic 4-7 should avoid inventing parallel runtime or decision state.

## 3. Epic 4-7 Current-State Assessment

## 3.1 Epic 4: Acceptance Judgment and Calibration

### What already exists

- acceptance evaluator and prompt composer:
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/acceptance/prompt_composer.py`
- browser evidence and filing:
  - `src/spec_orch/services/acceptance/browser_evidence.py`
  - `src/spec_orch/services/acceptance/linear_filing.py`
- mission-round acceptance orchestration is already real:
  - `src/spec_orch/services/round_orchestrator.py`
- mission acceptance surfaces already exist:
  - `src/spec_orch/dashboard/surfaces.py`
  - `src/spec_orch/dashboard/missions.py`
  - `src/spec_orch/dashboard/routes.py`
- retained judgment-model drafts imported from `codexharness`:
  - `docs/plans/imports/codexharness-2026-03-29/2026-03-29-acceptance-judgment-model.md`
  - `docs/plans/imports/codexharness-2026-03-29/constitutions.py`

### What now exists

- visible `acceptance_core/` package
- canonical judgment object family for:
  - `confirmed_issue`
  - `candidate_finding`
  - `observation`
- canonical routing policy objects for:
  - `verify`
  - `replay`
  - `explore`
  - `recon`
- a `decision_core`-compatible disposition seam
- dashboard surface pack v1 primitives
- a comparative calibration harness baseline
- a candidate-to-fixture graduation audit trail

### New semantic inputs

Epic 4 now has three canonical design references that update the meaning of the
baseline implementation:

- `docs/plans/2026-03-30-acpx-agentic-graphs-epic-4-alignment.md`
- `docs/plans/2026-03-30-acceptance-routing-policy.md`
- `docs/plans/2026-03-30-candidate-findings-review-sop.md`

These documents sharpen Epic 4 around:

- `workflow tuning` as a first-class harness activity
- `graph_profile` as part of routing/judgment provenance
- stepwise evidence and structured intermediate artifacts
- `candidate_finding` provenance and promotion discipline
- compare calibration that includes field drift and step-artifact drift

### Planning conclusion

Epic 4 semantic rebase is now part of the landed baseline.

Current status:

- `acceptance_core` baseline landed
- routing semantics rebased around:
  - `base_run_mode`
  - `budget_profile`
  - `graph_profile`
  - `evidence_plan`
  - `risk_posture`
- candidate findings now preserve provenance for:
  - `finding_id`
  - `baseline_ref`
  - `origin_step`
  - `graph_profile`
  - `run_mode`
  - `compare_overlay`
- compare calibration now supports:
  - field drift
  - selected step-artifact drift
  - graph-profile drift

Epic 4 is now a stronger semantic baseline for the later epics rather than only
a thin acceptance seam.

However, Epic 4 is not yet "design-complete" against the three canonical
references. The remaining gaps are tracked in:

- `docs/plans/2026-03-30-epic-4-semantic-completion-tranche.md`

## 3.2 Epic 5: Memory and Learning Linkage

### What already exists

- accepted memory ADR:
  - `docs/adr/0001-memory-architecture.md`
- file-backed memory service and recorder:
  - `src/spec_orch/services/memory/service.py`
  - `src/spec_orch/services/memory/recorder.py`
  - `src/spec_orch/services/memory/types.py`
- derivation and analytics helpers:
  - `src/spec_orch/services/memory/derivation.py`
  - `src/spec_orch/services/memory/analytics.py`
- `ContextAssembler` already injects memory-derived learnings

### What now exists

- memory recorder now ingests:
  - normalized `ExecutionOutcome`
  - `DecisionRecord`
  - `DecisionReview`
  - reviewed acceptance judgments
- reviewed learning views now exist for:
  - decision failures
  - decision recipes
  - reviewed acceptance findings
- provenance-aware latest-first recall now distinguishes:
  - reviewed
  - unreviewed
- `ContextAssembler` can now inject reviewed decision and acceptance learnings
  into planner/reviewer/supervisor/scoper node context

### Planning conclusion

Epic 5 baseline is aligned with the Epic 4 semantic rebase.

Memory and context linkage now ingest and recall:

- normalized `ExecutionOutcome`
- `DecisionRecord`
- `DecisionReview`
- reviewed acceptance findings with provenance fields from the rebased
  candidate-finding model

Do not grow more ad hoc ingestion paths before moving to Epic 6.

## 3.3 Epic 6: Evolution and Policy Promotion Linkage

### What already exists

- evolver framework and lifecycle trigger:
  - `src/spec_orch/services/evolution/evolution_trigger.py`
  - `src/spec_orch/services/evolution/evolution_policy.py`
- existing evolvers:
  - `prompt_evolver.py`
  - `intent_evolver.py`
  - `flow_policy_evolver.py`
  - `gate_policy_evolver.py`
  - `skill_evolver.py`
  - `config_evolver.py`
- promotion semantics already exist in parts of:
  - `src/spec_orch/services/gate_service.py`
  - `src/spec_orch/services/promotion_service.py`

### What is still missing

- evolvers do not consume normalized execution/decision evidence as first-class
  inputs
- no review-gated promotion requirement for high-impact assets
- no explicit supersession / rollback semantics for promoted assets
- no observability that says whether a promoted change came from:
  - execution evidence
  - reviewed decisions
  - reviewed acceptance findings
  - self-reflection only

### Planning conclusion

Epic 6 baseline is now landed on top of the Epic 5 learning views.

What now exists:

- normalized evolution signal bridging:
  - `src/spec_orch/services/evolution/signal_bridge.py`
- `EvolutionTrigger` journal entries now preserve:
  - `signal_origins`
  - `reviewed_evidence_count`
  - `promotion_origin`
- prompt evolution now consumes reviewed:
  - decision failures
  - decision recipes
  - acceptance findings
- high-impact promotions now pass through a review-aware promotion gate
- explicit file-backed promotion lifecycle state now exists for:
  - active promotion
  - supersession
  - rollback
- promotion observability is now explicit in both:
  - `.spec_orch_evolution/promotion_registry.json`
  - `evolution_journal.jsonl`

Epic 6 therefore no longer depends on future ad hoc evolution semantics.
Epic 7 can now be planned against a repo that has:

- normalized execution evidence
- normalized decision evidence
- acceptance judgment provenance
- governed policy/prompt promotion state

## 3.4 Epic 7: Contract Core Extraction and Surface Cleanup

### What already exists

- task-contract domain object:
  - `src/spec_orch/domain/task_contract.py`
- spec snapshot service:
  - `src/spec_orch/services/spec_snapshot_service.py`
- spec importers:
  - `src/spec_orch/spec_import/*`
- CLI pathways for spec/questions/freeze:
  - `src/spec_orch/cli/spec_commands.py`
  - `src/spec_orch/services/conversation_service.py`
- planner-driven question/answer flow:
  - `src/spec_orch/services/litellm_planner_adapter.py`

### What is still missing

- no visible `contract_core/` package
- contract and freeze logic still split across:
  - domain object
  - snapshot service
  - planner adapter
  - CLI commands
  - conversation freeze
- question/answer recording is still shell-driven rather than core-owned
- spec import and normalization still live outside a visible contract seam

### Planning conclusion

Epic 7 should remain last in sequence. It depends on the post-acceptance,
post-memory, post-evolution seams being stable enough that surface cleanup
won't immediately churn again.

## 4. Recommended Program Order

The recommended sequence stays the same, but the execution posture changes:

1. Epic 4: Acceptance Judgment and Calibration
2. Epic 5: Memory and Learning Linkage
3. Epic 6: Evolution and Policy Promotion Linkage
4. Epic 7: Contract Core Extraction and Surface Cleanup

The important correction is:

- Epic 4 is no longer “design only”
- Epic 5 is no longer “generic memory enhancement”
- Epic 6 is no longer “turn on evolvers”
- Epic 7 is no longer “late cleanup only”

Each of these epics must now explicitly consume the extracted cores.

## 5. New Tranche Plan

## 5.1 Tranche D: Epic 4 Foundation

This tranche is no longer merely a foundation checkpoint. It now also owns the
semantic rebase implied by the three Epic 4 design documents listed above.

This should be the next implementation tranche.

### Goal

Create the first stable `acceptance_core` seam without rewriting the entire
acceptance stack.

### Scope

1. Create `acceptance_core/` package skeleton
2. Define canonical judgment models
3. Define routing policy models
4. Define candidate-finding schema and review state machine
5. Bridge acceptance dispositions into `decision_core`

### Expected files

- `src/spec_orch/acceptance_core/__init__.py`
- `src/spec_orch/acceptance_core/models.py`
- `src/spec_orch/acceptance_core/routing.py`
- `src/spec_orch/acceptance_core/disposition.py`
- `src/spec_orch/acceptance_core/calibration.py`
- compat/wrapper updates in:
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/dashboard/surfaces.py`

### Explicit non-goals

- no dashboard redesign
- no broad `round_orchestrator` rewrite
- no fixture graduation automation yet

## 5.2 Tranche E: Epic 4 Surface + Calibration Completion

### Goal

Finish Epic 4 after the object seam exists.

### Scope

1. dashboard surface pack v1
2. compare overlay semantics
3. comparative calibration harness
4. candidate-to-fixture graduation trail

### Status

Implemented baseline.

## 5.3 Tranche F: Epic 5 Memory Linkage

### Goal

Make memory consume reviewed execution, decision, and acceptance state.

### Scope

1. add normalized `ExecutionOutcome` ingestion
2. add `DecisionRecord` / `DecisionReview` ingestion
3. add acceptance-judgment ingestion
4. add reviewed-decision learning views
5. inject reviewed learnings into `ContextAssembler`

## 5.4 Tranche G: Epic 6 Evolution Linkage

### Goal

Make promotion logic depend on reviewed evidence rather than raw episodic tags.

### Scope

1. evolution trigger consumes normalized outcome / decision / acceptance signals
2. prompt / intent / policy evolvers consume reviewed learnings
3. add promotion review gate
4. add supersession / rollback semantics
5. add promotion observability

## 5.5 Tranche H: Epic 7 Contract Core

### Goal

Extract `contract_core/` and thin surfaces.

### Scope

1. create `contract_core/`
2. move snapshot/freeze logic into it
3. move question/answer/decision recording into it
4. move `spec_import/*` normalization behind it
5. run surface cleanup pass across CLI / daemon / dashboard

## 6. Immediate Start Recommendation

Start with Tranche G.

That means:

- do not expand memory linkage beyond the new reviewed-evidence seam
- start evolution linkage on top of reviewed memory outputs
- do not start contract extraction yet

Epic 4 and Epic 5 are now the completed baselines for the next batch.

The next real implementation batch should be:

1. make evolution trigger consume reviewed execution/decision/acceptance signals
2. make evolvers consume reviewed learning views instead of raw episodic tags
3. add promotion review gates and rollback semantics
4. add promotion observability over reviewed evidence provenance

## 7. Definition of Success For This Replan

This replan succeeds if:

- Epic 4 becomes a real code tranche instead of a side design thread
- Epic 5 explicitly depends on reviewed judgment outputs
- Epic 6 explicitly starts from reviewed learning outputs
- Epic 7 is deferred until the higher-order seams stop moving
- no new parallel ontology is introduced outside:
  - `runtime_core`
  - `decision_core`
  - future `acceptance_core`
  - future `contract_core`
