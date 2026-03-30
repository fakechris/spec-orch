# Acceptance Judgment Linear Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fold acceptance judgment work into the current architecture program so Leader can manage one coherent dependency graph instead of two competing restructures.

**Architecture:** The existing program already organizes the repo around shared semantics, runtime-core extraction, decision-core extraction, and later memory/evolution/surface cleanup. Acceptance judgment should not remain an external side program. It should be inserted as a new program-level Epic immediately after `Decision Core Extraction`, because it depends on shared execution and decision seams and in turn becomes the most important consumer of memory, calibration, and surface cleanup work.

**Tech Stack:** Linear epics/issues, existing architecture plans in `docs/plans/`, Python 3.13 runtime, acceptance harness, dashboard/operator-console surfaces.

## 1. Executive Recommendation

Add a new program-level Epic:

`Epic 4: Acceptance Judgment and Calibration`

and renumber later epics forward.

### Revised program order

1. `Epic 1: Shared Execution Semantics`
2. `Epic 2: Runtime Core Extraction`
3. `Epic 3: Decision Core Extraction`
4. `Epic 4: Acceptance Judgment and Calibration`
5. `Epic 5: Memory and Learning Linkage`
6. `Epic 6: Evolution and Policy Promotion Linkage`
7. `Epic 7: Contract Core Extraction and Surface Cleanup`

## 2. Why Add a New Epic Instead of Scattering Work

Acceptance judgment is too large to hide as small tasks under unrelated epics.

If it is scattered:

- routing logic may land before decision semantics exist
- candidate-finding review can be modeled inconsistently
- compare/calibration work may be treated as dashboard polish instead of core capability
- memory/evolution dependencies will be unclear

If it is its own Epic:

- the dependency on `runtime_core` and `decision_core` stays explicit
- the output contract for memory/evolution consumers can be planned cleanly
- dashboard-specific work can be correctly framed as `surface pack v1`, not as the whole feature

## 3. Revised Epic Cards

### Epic 4

**Title:** `Acceptance Judgment and Calibration`

**Summary:**  
Define and land the judgment layer for acceptance on top of shared execution and decision seams. Introduce acceptance routing policy, candidate-finding and observation semantics, disposition workflow, compare overlay support, and the first dashboard surface pack with comparative calibration assets.

**Priority:** `P1`

**Depends on:** `Shared Execution Semantics`, `Runtime Core Extraction`, `Decision Core Extraction`

**Labels:** `arch-extraction`, `acceptance-judgment`, `calibration`, `surface-pack`

### Epic 5

No semantic change, but now depends on `Acceptance Judgment and Calibration`.

### Epic 6

No semantic change, but now depends on `Memory and Learning Linkage`.

### Epic 7

No semantic change, but now depends on the earlier six epics being stable enough not to churn its surface cleanup immediately.

## 4. Issues Under Epic 4

### E4-I1: Define acceptance judgment model

**Priority:** `P0`

**Labels:** `acceptance-judgment`

**Depends on:** `Decision Core Extraction`

**Summary:**  
Define the canonical judgment model for acceptance, including base run modes, compare overlay, judgment classes, and workflow states.

**Acceptance Criteria:**
- `Acceptance Judgment Model` doc exists
- canonical terms are fixed:
  - `verify / replay / explore / recon`
  - `confirmed_issue / candidate_finding / observation`
  - `queued / reviewed / promoted / dismissed / archived`
- `held` is explicitly demoted from ontology to workflow wording

**Out of Scope:**
- production queue implementation
- dashboard-specific fixtures

### E4-I2: Define acceptance routing policy

**Priority:** `P0`

**Labels:** `acceptance-judgment`, `routing`

**Depends on:** `Define acceptance judgment model`

**Summary:**  
Specify how the harness auto-routes new requests based on business goal, target, hard constraints, contract strength, surface familiarity, baseline availability, and judgment risk.

**Acceptance Criteria:**
- `Acceptance Routing Policy` doc exists
- automatic routing to `verify / replay / explore / recon` is defined
- user input contract is reduced to `goal + target + constraints`
- fallback recon behavior is defined

**Out of Scope:**
- runtime code landing

### E4-I3: Define candidate-finding object model and review SOP

**Priority:** `P0`

**Labels:** `acceptance-judgment`, `triage`

**Depends on:** `Define acceptance judgment model`

**Summary:**  
Define the minimum schema and review protocol for uncertain exploratory findings so they can be reviewed, promoted, dismissed, deduped, and archived without being confused with raw observations.

**Acceptance Criteria:**
- `Candidate Findings Review SOP` doc exists
- required fields are defined:
  - `claim`
  - `surface/route`
  - `evidence refs`
  - `confidence`
  - `impact_if_true`
  - `repro_status`
  - `hold_reason`
  - `promotion_test`
  - `recommended_next_step`
  - `dedupe_key`
- queue state transitions are defined

**Out of Scope:**
- compare fixtures

### E4-I4: Add decision-core-compatible disposition seam

**Priority:** `P1`

**Labels:** `acceptance-judgment`, `decision-core`

**Depends on:** `Decision Core Extraction`, `Define candidate-finding object model and review SOP`

**Summary:**  
Land the minimum runtime seam so candidate findings and review states plug into `decision_core` rather than inventing a parallel acceptance-owned review object.

**Acceptance Criteria:**
- acceptance disposition objects route through the decision seam
- no duplicate acceptance-only review lifecycle appears in legacy services
- unit tests lock object placement and state transitions

**Out of Scope:**
- dashboard UI work

### E4-I5: Define dashboard surface pack v1

**Priority:** `P1`

**Labels:** `acceptance-judgment`, `surface-pack`, `dashboard`

**Depends on:** `Define acceptance routing policy`

**Summary:**  
Define the first surface-specific acceptance pack for the operator console, including critique axes, route seeds, safe-action budget, baseline traces, and gold judgment expectations.

**Acceptance Criteria:**
- `Dashboard Surface Pack v1` doc exists
- dashboard critique axes are fixed
- seed routes and safe-action budget are defined
- baseline evidence shape is documented

**Out of Scope:**
- generalization to all surfaces

### E4-I6: Add comparative calibration harness

**Priority:** `P1`

**Labels:** `acceptance-judgment`, `calibration`

**Depends on:** `Define dashboard surface pack v1`

**Summary:**  
Introduce the compare overlay and the first comparative calibration harness so dashboard judgments can be rerun, compared, and tracked for regression.

**Acceptance Criteria:**
- compare overlay is represented explicitly
- dashboard fixture set exists
- baseline-vs-current judgment comparison is possible
- compare run output schema is documented or implemented

**Out of Scope:**
- broad multi-surface rollout

### E4-I7: Add candidate-to-fixture graduation loop

**Priority:** `P2`

**Labels:** `acceptance-judgment`, `calibration`, `memory-linkage`

**Depends on:** `Add comparative calibration harness`, `Memory and Learning Linkage`

**Summary:**  
Define how repeated or validated candidate findings graduate into fixture candidates and then into stable regression assets.

**Acceptance Criteria:**
- graduation rules are explicit
- repeated candidate findings can become fixture candidates
- fixture-candidate promotion leaves an audit trail

**Out of Scope:**
- cross-surface scale-out

## 5. What This Means for the Existing Epics

### Epic 3: Decision Core Extraction

No longer stops at generic supervision semantics.
It must now leave behind a seam that can host:

- review queue primitives
- disposition-compatible record types
- intervention-linked review state

### Epic 5: Memory and Learning Linkage

Must be prepared to ingest:

- candidate findings
- promotion / dismissal outcomes
- fixture graduation signals

This is a cleaner dependency than treating those as later dashboard-only concerns.

### Epic 7: Contract Core Extraction and Surface Cleanup

Should explicitly include:

- migration of dashboard/operator-console surfaces to consume the new acceptance judgment seam
- removal of old acceptance-specific ad hoc wording once dashboard surface pack v1 is stable

## 6. Immediate Leader Actions

Leader should do these next, in order:

1. Add the new Epic 4 into Linear
2. Shift old Epics 4-6 to 5-7
3. Record the dependency changes
4. Create issue cards for E4-I1 through E4-I7
5. Mark E4-I1 through E4-I3 as doc-first planning tasks
6. Mark E4-I4 onward as code tasks blocked on Epic 3 output

## 7. Current Execution Recommendation

Until Epic 3 reaches a stable first seam:

- continue acceptance judgment work as design/calibration planning
- do not launch broad runtime code changes for `SON-266` / `SON-267`
- allow isolated fixture/rubric experiments only if they do not define new durable package homes

This keeps both the architecture program and the acceptance program moving without letting them race each other into conflicting shapes.
