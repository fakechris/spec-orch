# Full Epic and Issue Breakdown

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the architecture and acceptance program into one dependency-correct Epic/Issue tree covering shared semantics, core extraction, acceptance judgment, and the later memory/evolution/contract follow-through.

**Architecture:** The program is no longer just “shared semantics then runtime extraction.” It is now a 7-epic extraction sequence: first shared execution semantics, then runtime-core structure, then decision-core structure, then acceptance judgment as the first major consumer of those seams, followed by memory/evolution linkage and finally contract/surface cleanup. Owners remain separate while shared primitives become explicit cores.

**Tech Stack:** Python 3.13, dataclasses, JSON/JSONL/Markdown carriers, current `src/spec_orch` layout, pytest, Linear for project management.

---

## 1. Why This Breakdown Exists

Right now the repo has:

- architecture recovery docs
- semantic model plans
- runtime extraction plans
- acceptance judgment alignment plans
- first-week implementation tranches

But it still needs one canonical Epic tree that preserves dependency order across the whole program.

If acceptance is left outside the tree or memory/evolution are planned as if acceptance does not exist:

- decision-core will stop at generic supervision semantics
- acceptance will keep growing on legacy seams
- memory/evolution will plan around the wrong upstream objects
- Linear sequencing will drift immediately

This document fixes that.

## 2. Program-Level Epic Order

The full program should now be managed as these Epics, in order:

1. `Epic 1: Shared Execution Semantics`
2. `Epic 2: Runtime Core Extraction`
3. `Epic 3: Decision Core Extraction`
4. `Epic 4: Acceptance Judgment and Calibration`
5. `Epic 5: Memory and Learning Linkage`
6. `Epic 6: Evolution and Policy Promotion Linkage`
7. `Epic 7: Contract Core Extraction and Surface Cleanup`

This is the canonical order.

### Dependency rule

- Epic 2 depends on Epic 1
- Epic 3 depends on Epics 1-2
- Epic 4 depends on Epics 1-3
- Epic 5 depends on Epics 3-4
- Epic 6 depends on Epic 5
- Epic 7 depends on Epics 1-6 being structurally stable enough that contract and surface cleanup will not churn immediately

---

## 3. Epic 1: Shared Execution Semantics

**Purpose:** Create the shared execution language before changing package structure.

**Source plans:**

- [`2026-03-29-shared-execution-semantics-rollout.md`](./2026-03-29-shared-execution-semantics-rollout.md)
- [`../architecture/shared-execution-semantics.md`](../architecture/shared-execution-semantics.md)
- [`../architecture/execution-outcome-artifact-mapping.md`](../architecture/execution-outcome-artifact-mapping.md)

**Deliverables:**

- domain-level semantic types
- read-side normalization
- consumer migration
- dual-write support
- canonical write cutover plan

### Issues under Epic 1

#### E1-I1: Add shared execution semantic models

Maps to:

- Phase 1 Task 1

Outputs:

- `domain/execution_semantics.py`
- model tests

#### E1-I2: Add read-side normalizers

Maps to:

- Phase 1 Task 2

Outputs:

- issue read normalizer
- mission leaf read normalizer
- mission round read normalizer

#### E1-I3: Migrate read-side consumers

Maps to:

- Phase 1 Task 3

Outputs:

- dashboard readers prefer normalized reads
- analytics prefer normalized reads
- context assembly can consume normalized artifact refs

#### E1-I4: Add issue-path dual-write

Maps to:

- Phase 1 Task 4

Outputs:

- issue path writes normalized payloads alongside legacy carriers

#### E1-I5: Add mission leaf dual-write

Maps to:

- Phase 1 Task 5

Outputs:

- worker / packet execution writes normalized payloads alongside legacy carriers

#### E1-I6: Add mission round dual-write

Maps to:

- Phase 1 Task 6

Outputs:

- round supervision writes normalized payloads alongside legacy carriers

#### E1-I7: Reader cutover to normalized preference

Maps to:

- Phase 1 Task 7

Outputs:

- normalized readers become preferred read path
- legacy files remain as fallback

#### E1-I8: Canonical write cutover with bridge retention

Maps to:

- Phase 1 Task 8

Outputs:

- canonical normalized writer path
- explicit bridge retention policy

#### E1-I9: Validation matrix and stop conditions

Maps to:

- Phase 1 Task 9

Outputs:

- full verification pass
- documented cutover readiness

---

## 4. Epic 2: Runtime Core Extraction

**Purpose:** Turn shared execution semantics into a visible program structure so the codebase does not stop in a dangerous half-unified state.

**Source plans:**

- [`2026-03-29-runtime-extraction-phase-2.md`](./2026-03-29-runtime-extraction-phase-2.md)
- [`2026-03-29-first-week-implementation-tranches.md`](./2026-03-29-first-week-implementation-tranches.md)
- [`../architecture/core-extraction-migration-matrix.md`](../architecture/core-extraction-migration-matrix.md)

**Deliverables:**

- visible `runtime_core/`
- normalized readers and writers live there
- owners delegate into it
- consumers depend on it
- structural guard tests prevent regression

### Issues under Epic 2

#### E2-I1: Create runtime-core package skeleton

Maps to:

- Phase 2 Task 1
- First-week Tranche 1 runtime-core half

Outputs:

- `runtime_core/__init__.py`
- `runtime_core/models.py`
- `runtime_core/paths.py`
- `runtime_core/readers.py`
- `runtime_core/writers.py`
- `runtime_core/supervision.py`
- `runtime_core/adapters.py`

#### E2-I2: Move normalized read logic into runtime-core

Maps to:

- Phase 2 Task 2
- First-week Tranche 3 read seam half

Outputs:

- `services/execution_semantics_reader.py` becomes shim
- real implementation in `runtime_core/readers.py`

#### E2-I3: Move normalized write logic into runtime-core

Maps to:

- Phase 2 Task 3
- First-week Tranche 3 write seam half

Outputs:

- `services/execution_semantics_writer.py` becomes shim
- real implementation in `runtime_core/writers.py`

#### E2-I4: Delegate issue owner to runtime-core

Maps to:

- Phase 2 Task 4
- First-week Tranche 4 issue-owner half

Outputs:

- `RunController` no longer hand-builds normalized payloads

#### E2-I5: Delegate mission leaf owners to runtime-core

Maps to:

- Phase 2 Task 5
- First-week Tranche 4 mission-owner half

Outputs:

- worker handles / packet executor delegate normalized writes

#### E2-I6: Delegate round supervision shaping to runtime-core

Maps to:

- Phase 2 Task 6

Outputs:

- round payload shaping centralized
- round owner still preserved

#### E2-I7: Migrate consumers to runtime-core facades only

Maps to:

- Phase 2 Task 7

Outputs:

- readers and consumers stop using service-local interpretation logic

#### E2-I8: Add structural guard tests

Maps to:

- Phase 2 Task 8

Outputs:

- tests that enforce runtime-core seam ownership

#### E2-I9: Runtime-core package boundary review

Maps to:

- Phase 2 Task 9

Outputs:

- explicit package-boundary audit
- unresolved structural leaks documented before moving on

---

## 5. Epic 3: Decision Core Extraction

**Purpose:** Extract a first-class supervision and decision layer instead of leaving decision semantics split across round owners, dashboard approvals, and event logs.

**Source plans:**

- [`2026-03-29-system-primitives-implementation-track.md`](./2026-03-29-system-primitives-implementation-track.md)
- [`2026-03-29-first-week-implementation-tranches.md`](./2026-03-29-first-week-implementation-tranches.md)
- [`../architecture/system-primitives-and-high-level-organization.md`](../architecture/system-primitives-and-high-level-organization.md)

**Deliverables:**

- visible `decision_core/`
- `DecisionPoint` inventory
- `DecisionRecord`
- `Intervention`
- mission round path as first adopter
- acceptance-compatible review/disposition seam

### Issues under Epic 3

#### E3-I1: Create decision-core package skeleton

Maps to:

- First-week Tranche 1 decision-core half

Outputs:

- `decision_core/__init__.py`
- `decision_core/models.py`
- `decision_core/records.py`
- `decision_core/interventions.py`
- `decision_core/review_queue.py`

#### E3-I2: Define decision primitives and inventory

Maps to:

- First-week Tranche 5

Outputs:

- `DecisionPoint`
- `DecisionRecord`
- `Intervention`
- initial inventory:
  - rule-owned
  - LLM-owned
  - human-required

#### E3-I3: Integrate mission supervision with decision-core writes

Maps to:

- First-week Tranche 6 supervisor half

Outputs:

- supervisor round review emits `DecisionRecord`
- `ask_human` becomes explicit intervention artifact

#### E3-I4: Migrate approval queue to decision-core review state

Maps to:

- First-week Tranche 6 dashboard half

Outputs:

- approvals use `decision_core` state rather than ad hoc derivation helpers

#### E3-I5: Expand decision inventory to non-mission LLM decision points

Maps to:

- recovery work from `evolution-trigger-architecture.md`

Outputs:

- issue path decision points classified
- flow/router/reviewer/conductor points classified

#### E3-I6: Add decision review schema

Outputs:

- `DecisionReview`
- human review result
- self-reflection result
- escalation judgment fields

---

## 6. Epic 4: Acceptance Judgment and Calibration

**Purpose:** Make acceptance judgment a first-class program layer on top of `runtime_core` and `decision_core` instead of letting it continue as an ad hoc expansion of legacy service seams.

**Source plans:**

- [`2026-03-29-acceptance-judgment-linear-integration.md`](./2026-03-29-acceptance-judgment-linear-integration.md)
- [`2026-03-29-acceptance-judgment-and-core-extraction-alignment.md`](./2026-03-29-acceptance-judgment-and-core-extraction-alignment.md)
- [`imports/codexharness-2026-03-29/2026-03-29-acceptance-judgment-model.md`](./imports/codexharness-2026-03-29/2026-03-29-acceptance-judgment-model.md)
- [`imports/codexharness-2026-03-29/2026-03-29-son-264-runtime-responsibility-split.md`](./imports/codexharness-2026-03-29/2026-03-29-son-264-runtime-responsibility-split.md)

**Deliverables:**

- acceptance judgment ontology
- acceptance routing policy
- candidate-finding review protocol
- decision-core-compatible disposition seam
- dashboard surface pack v1
- comparative calibration harness
- candidate-to-fixture graduation loop

### Issues under Epic 4

#### E4-I1: Define acceptance judgment model

Outputs:

- canonical terms fixed for:
  - `verify / replay / explore / recon`
  - `confirmed_issue / candidate_finding / observation`
  - `queued / reviewed / promoted / dismissed / archived`
- `held` demoted from ontology to workflow wording

#### E4-I2: Define acceptance routing policy

Outputs:

- explicit routing to `verify / replay / explore / recon`
- reduced user input contract:
  - `goal`
  - `target`
  - `constraints`
- fallback recon behavior

#### E4-I3: Define candidate-finding object model and review SOP

Outputs:

- minimum candidate-finding schema
- review / dedupe / promotion / dismissal workflow
- queue state transitions

#### E4-I4: Add decision-core-compatible disposition seam

Outputs:

- acceptance disposition uses `decision_core`
- no duplicate acceptance-only review lifecycle in legacy services

#### E4-I5: Define dashboard surface pack v1

Outputs:

- dashboard critique axes
- route seeds
- safe-action budget
- baseline evidence shape

#### E4-I6: Add comparative calibration harness

Outputs:

- compare overlay semantics
- dashboard fixture set
- baseline-vs-current judgment comparison path

#### E4-I7: Add candidate-to-fixture graduation loop

Outputs:

- graduation rules
- audit trail for fixture promotion
- explicit bridge from reviewed candidates into stable regression assets

---

## 7. Epic 5: Memory and Learning Linkage

**Purpose:** Make execution outcomes, decision records, and reviewed acceptance judgments feed a coherent learning loop instead of storing only fragmented evidence.

**Source inputs:**

- [`../architecture/evolution-trigger-architecture.md`](../architecture/evolution-trigger-architecture.md)
- [`../architecture/system-primitives-and-high-level-organization.md`](../architecture/system-primitives-and-high-level-organization.md)
- [`../adr/0001-memory-architecture.md`](../adr/0001-memory-architecture.md)
- [`../specs/memory-vnext/adr-0002-memory-vnext.md`](../specs/memory-vnext/adr-0002-memory-vnext.md)

**Deliverables:**

- decision-aware memory recording
- acceptance-aware memory recording
- learning views over decisions and outcomes
- latest-first reviewed-decision recall
- context injection of prior decision and acceptance cases

### Issues under Epic 5

#### E5-I1: Extend memory recorder for normalized execution outcomes

Outputs:

- memory ingestion from normalized outcome schema rather than only legacy report payloads

#### E5-I2: Extend memory recorder for decision records

Outputs:

- decision records stored as episodic/semantic learnings where appropriate

#### E5-I3: Add reviewed-decision learning views

Outputs:

- decision failure patterns
- decision success recipes
- reviewed intervention histories

#### E5-I4: Inject decision-related learnings into context assembly

Outputs:

- role-aware learning injection for planner / reviewer / supervisor / scoper

#### E5-I5: Add provenance-aware recall for decisions and outcomes

Outputs:

- latest-first recall
- reviewed-vs-unreviewed distinction
- clearer provenance in injected context

---

## 8. Epic 6: Evolution and Policy Promotion Linkage

**Purpose:** Make reviewed execution, decision, and acceptance evidence promotable into system assets: prompts, policies, skills, strategies, and rules.

**Source inputs:**

- current `services/evolution/*`
- `evolution-trigger-architecture.md`
- memory linkage outputs from Epic 5
- retained `codexharness` role-constitution patch bundle

**Deliverables:**

- evolvers consume normalized evidence
- role constitutions and prompt discipline are preserved as promotion inputs
- promotion policy distinguishes evidence quality
- review gates exist before auto-promotion

### Issues under Epic 6

#### E6-I1: Make evolution triggers consume normalized outcome and decision signals

Outputs:

- evolution trigger policy no longer depends only on legacy report-derived summaries

#### E6-I2: Add decision-aware prompt evolution inputs

Outputs:

- prompt evolver can use reviewed decision failures and successes

#### E6-I3: Add policy/skill promotion review gate

Outputs:

- reviewed evidence required before promotion of high-impact policy assets

#### E6-I4: Add supersession and rollback semantics for promoted assets

Outputs:

- promotion is no longer append-only
- stale or harmful promoted assets can be superseded cleanly

#### E6-I5: Add evolution observability over reviewed decisions

Outputs:

- track which promoted changes came from:
  - execution evidence
  - reviewed decisions
  - self-reflection only

---

## 9. Epic 7: Contract Core Extraction and Surface Cleanup

**Purpose:** Finish the architectural line by extracting contract-specific concerns and cleaning surface modules so they consume cores rather than encode business truth.

**Source inputs:**

- `spec_snapshot_service.py`
- `domain/task_contract.py`
- `spec_import/*`
- `cli/spec_commands.py`
- dashboard and daemon surfaces after Epics 1-6

**Deliverables:**

- visible `contract_core/`
- contract normalization boundary
- thinner surface modules
- fewer object definitions tied to shells and carriers

### Issues under Epic 7

#### E7-I1: Create contract-core package skeleton

Outputs:

- `contract_core/` home established

#### E7-I2: Extract contract snapshot and freeze logic

Outputs:

- snapshot/freeze logic no longer lives as service-local behavior only

#### E7-I3: Extract question/answer/decision recording for specs

Outputs:

- contract decisions stop living in CLI pathways only

#### E7-I4: Move spec import and normalization behind contract-core

Outputs:

- spec importers become contract-core concerns

#### E7-I5: Surface cleanup pass

Outputs:

- dashboard, CLI, and daemon consume core seams more consistently
- fewer cross-core leaks remain in `services/`

---

## 10. First-Week Work Mapped Into This Epic Tree

The already-defined first-week tranches fit into the full tree like this:

- Tranche 1
  - E2-I1
  - E3-I1

- Tranche 2
  - E1-I1 continuation for model hardening
  - E2-I1 / E2-I2 preparation

- Tranche 3
  - E2-I2
  - E2-I3

- Tranche 4
  - E2-I4
  - E2-I5

- Tranche 5
  - E3-I2

- Tranche 6
  - E3-I3
  - E3-I4

That is why the first-week slice is valid, but still not the whole program.

---

## 11. Minimum Linear Structure To Create

Before implementation starts, Linear should contain at least:

- 7 Epics
- all Issues listed in this document under each Epic

Recommended minimum issue count:

- Epic 1: 9 issues
- Epic 2: 9 issues
- Epic 3: 6 issues
- Epic 4: 7 issues
- Epic 5: 5 issues
- Epic 6: 5 issues
- Epic 7: 5 issues

Total recommended initial issue set: **46 issues**

This number is intentionally explicit so the program is not under-managed by abstraction.

---

## 12. Issue Template For Linear

Each Linear issue created from this document should include:

- Epic
- exact title from this breakdown
- source plan/doc references
- files expected to change
- acceptance criteria
- tests to run
- explicit dependencies on prior issues
- explicit non-goals
- whether the issue is:
  - `extract-now`
  - `wrap-now`
  - `leave-for-later`

---

## 13. Final Rule

From this point on:

- no later Epic should be created in isolation from earlier Epics
- no coding tranche should be scheduled without its parent Epic existing
- no new structural abstraction should be proposed without first placing it in this Epic tree
- no acceptance-judgment planning should proceed outside this 7-epic program shape
