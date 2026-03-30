# Acceptance Judgment and Core Extraction Alignment Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align acceptance judgment work (`SON-266` / `SON-267`) with the ongoing `runtime_core` and `decision_core` extraction so the two programs can advance together without creating overlapping seams or duplicate ontologies.

**Architecture:** The acceptance program has reached the point where it needs first-class judgment objects, routing policy, and calibration assets. The architecture program is simultaneously extracting `runtime_core` and `decision_core` as the shared seams for execution and supervision. This plan treats acceptance judgment as a dependent layer on top of those seams: documentation and object-model alignment can proceed now, but broad code landing should wait for the core extraction path to stabilize.

**Tech Stack:** Python 3.13, existing `src/spec_orch` package layout, dashboard/operator-console acceptance harness, JSON/JSONL artifacts, pytest, Linear epic/issue planning.

## 1. Why These Two Programs Must Be Aligned

The current acceptance work is no longer "just evaluator polish." It is defining:

- runtime routing for `verify / replay / explore / recon`
- judgment classes such as `confirmed_issue`, `candidate_finding`, and `observation`
- workflow states such as `queued / reviewed / promoted / dismissed / archived`
- promotion rules from exploratory evidence into calibration assets

At the same time, the architecture work is defining:

- `runtime_core` for shared execution semantics
- `decision_core` for supervision, decision records, interventions, and review loops

If both programs independently land code now, the repo will almost certainly grow:

- two similar ontologies for decision state
- two similar persistence and queue seams
- two similar places to hang acceptance artifacts
- avoidable refactor churn when `decision_core` becomes the canonical home

So the question is not whether both programs should continue. They should. The question is where to draw the line between:

- what can be stabilized in docs immediately
- what can be prototyped in isolated fixtures
- what must wait for `runtime_core` / `decision_core`

## 2. Core Alignment Decision

Acceptance judgment should be treated as a dependent layer on top of core extraction.

The practical rule is:

- `runtime_core` defines execution attempts, outcomes, artifact refs, and normalized execution carriers
- `decision_core` defines supervision objects, decision records, interventions, and review/disposition semantics
- acceptance judgment defines how acceptance-specific evidence becomes routed, judged, queued, reviewed, and eventually calibrated

That means acceptance judgment is not a sibling architecture program competing with core extraction. It is the first major consumer that will pressure-test the extracted cores.

## 3. What Can Proceed Now

The following should proceed immediately:

- acceptance judgment documentation
- routing policy documentation
- surface-pack design
- candidate-finding schema design
- review SOP design
- calibration fixture design
- compare-overlay design

These produce clarity without locking the repo into premature code seams.

The following can also proceed in low-risk shadow form:

- isolated evaluator fixture experiments
- isolated prompt/rubric calibration
- documentation of dashboard surface-pack critique axes

These must avoid rewriting owner seams or inventing new durable package homes before the extraction plan lands.

## 4. What Should Wait

The following should wait until `runtime_core` and `decision_core` reach a stable first shape:

- broad `round_orchestrator` runtime rewrites for acceptance routing
- durable queue objects stored in ad hoc service modules
- UI-first candidate-finding workflow embedded directly into current dashboard surfaces
- long-lived code seams for disposition state in old service modules
- acceptance-specific persistence carriers invented outside the extracted cores

In other words: no large code landing for `SON-266` / `SON-267` should happen while the architecture work is still defining where execution and decision truth lives.

## 5. Collision Zones

These are the highest-risk overlap areas between the two programs:

### 5.1 `round_orchestrator.py`

Acceptance already uses it for:

- campaign generation
- exploratory routing
- workflow replay

The architecture program wants it to stop owning shared supervision shaping directly and delegate toward `decision_core`.

So acceptance should not harden a new permanent ontology here.

### 5.2 `litellm_supervisor_adapter.py`

Acceptance judgment wants:

- disposition semantics
- review states
- promotion logic

Architecture wants:

- decision records
- intervention semantics
- supervision inventory

These are adjacent enough that separate invention would be expensive to unwind.

### 5.3 shared domain model surface

Acceptance wants:

- candidate finding schema
- judgment class names

Architecture wants:

- clearer separation between domain objects, runtime objects, and decision objects

This means acceptance should avoid stuffing permanent cross-cutting state into generic legacy models until the package boundary is settled.

## 6. Recommended Ownership Split

### `runtime_core`

Should own:

- execution attempts
- execution outcomes
- artifact references
- normalized execution reads/writes
- continuity semantics

Acceptance should consume these objects, not redefine them.

### `decision_core`

Should own:

- decision records
- review state transitions
- intervention semantics
- review queue primitives
- disposition state carriers

Acceptance should plug its judgment classes and review lifecycle into this seam.

### acceptance-specific layer

Should own:

- acceptance routing policy
- acceptance judgment classes
- compare overlay semantics
- surface packs
- calibration fixtures
- promotion rules from exploratory evidence into regression assets

This layer should depend on the cores. It should not replace them.

## 7. Immediate Product-Language Corrections

The following language should now be treated as canonical:

- do **not** use `held` as the primary ontology
- use `candidate_finding` as the primary uncertain-judgment object
- treat `compare` as an overlay, not a sibling run mode
- keep `verify / replay / explore / recon` as base run modes
- keep `queued / reviewed / promoted / dismissed / archived` as workflow states

This naming should be aligned into the architecture program before code lands.

## 8. Recommended Sequence

### Phase A: doc-first alignment

Complete and circulate:

- `Acceptance Judgment Model`
- `Acceptance Routing Policy`
- `Dashboard Surface Pack v1`
- `Candidate Findings Review SOP`

No broad code landing yet.

### Phase B: core extraction

Proceed with:

- `Shared Execution Semantics`
- `Runtime Core Extraction`
- `Decision Core Extraction`

These are the code-critical prerequisites.

### Phase C: acceptance judgment code landing

Once `decision_core` has a stable review/disposition seam:

- land candidate-finding schema
- land routing and disposition logic
- connect compare overlay
- connect dashboard surface-pack v1

### Phase D: comparative calibration expansion

Only after the candidate-finding lifecycle is stable:

- widen fixtures
- add compare metrics
- graduate repeated candidates into regression assets

## 9. Decision

Adopt the following constraint immediately:

Acceptance judgment may continue as a design and calibration effort, but it should not become a broad code refactor program until `runtime_core` and `decision_core` establish the stable seam it needs.

That keeps both programs moving while avoiding conceptual and code-level collision.
