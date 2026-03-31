# Linear-Ready Epic Mapping

> 日期: 2026-03-29
> 状态: historical Linear creation mapping; current execution status must be
> read from Linear and 2026-03-30 reconciliation docs
> 目的: 把完整架构计划推进到可直接映射 Linear 的程度

---

## 1. 使用说明

这份文档不是新的架构方案，而是把 canonical 7-Epic program 整理成 Linear 可录入格式。

它基于：

- [`2026-03-29-full-epic-and-issue-breakdown.md`](./2026-03-29-full-epic-and-issue-breakdown.md)
- [`2026-03-29-acceptance-integrated-program-rebaseline.md`](./2026-03-29-acceptance-integrated-program-rebaseline.md)
- [`2026-03-29-acceptance-judgment-linear-integration.md`](./2026-03-29-acceptance-judgment-linear-integration.md)

目标是让后续只需要做两件事：

1. 在 Linear 中创建或更新 Epic
2. 按这里的 Issue 卡片逐条创建或更新

---

## 2. 建议 Linear 字段约定

建议统一使用以下字段：

### Epic 字段

- `Title`
- `Summary`
- `Priority`
- `Depends on`
- `Labels`

### Issue 字段

- `Title`
- `Epic`
- `Summary`
- `Priority`
- `Labels`
- `Depends on`
- `Acceptance Criteria`
- `Out of Scope`

### 建议标签

- `arch-extraction`
- `shared-semantics`
- `runtime-core`
- `decision-core`
- `acceptance-judgment`
- `calibration`
- `surface-pack`
- `memory-linkage`
- `evolution-linkage`
- `contract-core`
- `surface-cleanup`
- `dual-write`
- `shim`
- `cutover`

### 建议优先级语义

- `P0`
  - 当前 program 顺序上的阻塞项
- `P1`
  - 当前 Epic 内的主路径项
- `P2`
  - 同 Epic 内的后续项

---

## 3. Epic Cards

### Epic 1

**Title:** `Shared Execution Semantics`

**Summary:**  
Create the shared execution language for issue and mission paths before changing package structure. Introduce normalized execution objects, normalized readers, dual-write support, and controlled reader/writer cutover without merging runtime owners.

**Priority:** `P0`

**Depends on:** none

**Labels:** `arch-extraction`, `shared-semantics`

### Epic 2

**Title:** `Runtime Core Extraction`

**Summary:**  
Turn the shared execution semantics into a visible runtime-core package. Route normalized reads and writes through a dedicated seam and make owners delegate to it without unifying lifecycle ownership.

**Priority:** `P0`

**Depends on:** `Shared Execution Semantics`

**Labels:** `arch-extraction`, `runtime-core`, `shim`

### Epic 3

**Title:** `Decision Core Extraction`

**Summary:**  
Extract a first-class supervision and decision layer. Introduce decision primitives, decision recording, intervention semantics, and move mission supervision and approval flows onto that seam.

**Priority:** `P0`

**Depends on:** `Shared Execution Semantics`, `Runtime Core Extraction`

**Labels:** `arch-extraction`, `decision-core`

### Epic 4

**Title:** `Acceptance Judgment and Calibration`

**Summary:**  
Define and land the judgment layer for acceptance on top of shared execution and decision seams. Introduce acceptance routing policy, candidate-finding and observation semantics, disposition workflow, compare overlay support, and the first dashboard surface pack with comparative calibration assets.

**Priority:** `P1`

**Depends on:** `Shared Execution Semantics`, `Runtime Core Extraction`, `Decision Core Extraction`

**Labels:** `arch-extraction`, `acceptance-judgment`, `calibration`, `surface-pack`

### Epic 5

**Title:** `Memory and Learning Linkage`

**Summary:**  
Link normalized execution, decision, and reviewed acceptance artifacts into the memory system so reviewed outcomes and decision cases become recallable learning assets rather than fragmented evidence.

**Priority:** `P1`

**Depends on:** `Decision Core Extraction`, `Acceptance Judgment and Calibration`

**Labels:** `arch-extraction`, `memory-linkage`

### Epic 6

**Title:** `Evolution and Policy Promotion Linkage`

**Summary:**  
Make reviewed execution, decision, and acceptance evidence promotable into prompts, policies, skills, and strategy assets with explicit promotion and rollback semantics.

**Priority:** `P1`

**Depends on:** `Memory and Learning Linkage`

**Labels:** `arch-extraction`, `evolution-linkage`

### Epic 7

**Title:** `Contract Core Extraction and Surface Cleanup`

**Summary:**  
Extract contract-specific concerns into a visible contract core and thin CLI/dashboard/daemon surfaces so they consume core seams rather than encode business truth.

**Priority:** `P2`

**Depends on:** `Shared Execution Semantics`, `Runtime Core Extraction`, `Decision Core Extraction`, `Acceptance Judgment and Calibration`, `Memory and Learning Linkage`, `Evolution and Policy Promotion Linkage`

**Labels:** `arch-extraction`, `contract-core`, `surface-cleanup`

---

## 4. Issue Cards

下面按 Epic 顺序列出建议录入的 Issue。

### Epic 1: Shared Execution Semantics

#### E1-I1

**Title:** `Add shared execution semantic models`

**Priority:** `P0`

**Labels:** `arch-extraction`, `shared-semantics`

**Depends on:** none

**Summary:**  
Add domain-level semantic dataclasses and enums for normalized execution objects so issue and mission paths can speak the same execution language before any structural extraction begins.

**Acceptance Criteria:**
- `domain/execution_semantics.py` exists
- execution semantic tests cover enum/value constraints
- nullable review/gate/continuity fields are explicitly modeled

**Out of Scope:**
- runtime-core package extraction
- owner delegation

#### E1-I2

**Title:** `Add read-side normalizers for issue and mission artifacts`

**Priority:** `P0`

**Labels:** `arch-extraction`, `shared-semantics`

**Depends on:** `Add shared execution semantic models`

**Summary:**  
Introduce normalization adapters that can interpret current issue, mission worker, and mission round artifacts into shared execution semantics without requiring new files to exist yet.

**Acceptance Criteria:**
- issue workspace normalization works
- mission worker normalization works
- mission round normalization works
- tests use small fixtures and pass

**Out of Scope:**
- dual-write
- canonical write cutover

#### E1-I3

**Title:** `Migrate read-side consumers to normalized execution reads`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`

**Depends on:** `Add read-side normalizers for issue and mission artifacts`

**Summary:**  
Update dashboard, analytics, and context readers to prefer normalized reads while keeping legacy files as fallback.

**Acceptance Criteria:**
- dashboard consumers prefer normalized reads
- analytics consumers prefer normalized reads
- context assembler can consume normalized artifact refs

**Out of Scope:**
- writer changes

#### E1-I4

**Title:** `Add issue-path dual-write for normalized execution payloads`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`, `dual-write`

**Depends on:** `Migrate read-side consumers to normalized execution reads`

**Summary:**  
Make the issue path write normalized payloads alongside legacy carriers so read migration can be validated without immediate cutover.

**Acceptance Criteria:**
- issue run writes normalized payloads
- legacy artifacts still exist
- tests cover dual-write behavior

**Out of Scope:**
- legacy file removal

#### E1-I5

**Title:** `Add mission leaf dual-write for normalized execution payloads`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`, `dual-write`

**Depends on:** `Add issue-path dual-write for normalized execution payloads`

**Summary:**  
Make mission worker and packet execution paths write normalized payloads alongside legacy worker artifacts.

**Acceptance Criteria:**
- worker/packet execution writes normalized payloads
- legacy worker artifacts remain
- tests cover both continuity variants where applicable

**Out of Scope:**
- round-level supervision payloads

#### E1-I6

**Title:** `Add mission round dual-write for normalized supervision payloads`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`, `dual-write`

**Depends on:** `Add mission leaf dual-write for normalized execution payloads`

**Summary:**  
Make mission round supervision write normalized round/supervision payloads alongside current round artifacts.

**Acceptance Criteria:**
- round supervision writes normalized payloads
- existing round artifacts remain
- tests prove round is not treated as execution attempt

**Out of Scope:**
- decision-core extraction

#### E1-I7

**Title:** `Cut readers over to normalized execution preference`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`, `cutover`

**Depends on:** `Add mission round dual-write for normalized supervision payloads`

**Summary:**  
Make normalized artifacts the preferred read path for system consumers while preserving legacy fallbacks.

**Acceptance Criteria:**
- normalized reads are preferred by consumers
- legacy fallback remains functional
- regression tests cover missing normalized payload fallback

**Out of Scope:**
- canonical write-only mode

#### E1-I8

**Title:** `Cut canonical writes over to normalized execution payloads with bridge retention`

**Priority:** `P2`

**Labels:** `arch-extraction`, `shared-semantics`, `cutover`

**Depends on:** `Cut readers over to normalized execution preference`

**Summary:**  
Promote normalized execution writes to canonical status while explicitly retaining bridge/compatibility files until downstream migration is complete.

**Acceptance Criteria:**
- normalized write path is canonical
- bridge retention policy is documented
- legacy bridges remain where required

**Out of Scope:**
- runtime-core package extraction

#### E1-I9

**Title:** `Validate shared execution semantics rollout and stop conditions`

**Priority:** `P1`

**Labels:** `arch-extraction`, `shared-semantics`

**Depends on:** `Cut canonical writes over to normalized execution payloads with bridge retention`

**Summary:**  
Run the full validation matrix and confirm that Phase 1 stop conditions are satisfied before runtime-core extraction begins.

**Acceptance Criteria:**
- full validation suite defined in Phase 1 runs
- documented readiness to proceed to runtime-core extraction
- open risks and stop conditions updated

**Out of Scope:**
- runtime-core implementation

### Epic 2: Runtime Core Extraction

#### E2-I1

**Title:** `Create runtime-core package skeleton`

**Priority:** `P0`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Validate shared execution semantics rollout and stop conditions`

**Summary:**  
Create the visible package boundary for runtime-core so new execution semantic code has a canonical home.

**Acceptance Criteria:**
- `runtime_core/` package exists
- import tests pass
- package exports are stable enough for follow-on work

**Out of Scope:**
- moving all live logic immediately

#### E2-I2

**Title:** `Move normalized read logic behind runtime-core`

**Priority:** `P0`

**Labels:** `arch-extraction`, `runtime-core`, `shim`

**Depends on:** `Create runtime-core package skeleton`

**Summary:**  
Make runtime-core the real implementation for normalized reads and reduce the existing service reader to a compatibility shim.

**Acceptance Criteria:**
- `runtime_core/readers.py` owns real read logic
- service-level reader is a shim
- no duplicate independent read implementations remain

**Out of Scope:**
- write path migration

#### E2-I3

**Title:** `Move normalized write logic behind runtime-core`

**Priority:** `P0`

**Labels:** `arch-extraction`, `runtime-core`, `shim`

**Depends on:** `Move normalized read logic behind runtime-core`

**Summary:**  
Make runtime-core the real implementation for normalized writes and reduce the service writer to a compatibility shim.

**Acceptance Criteria:**
- `runtime_core/writers.py` owns real write logic
- path decisions come from `runtime_core/paths.py`
- service-level writer is a shim

**Out of Scope:**
- owner delegation

#### E2-I4

**Title:** `Delegate issue owner normalized shaping to runtime-core`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Move normalized write logic behind runtime-core`

**Summary:**  
Make `RunController` and issue-path helpers delegate normalized read/write shaping to runtime-core while keeping issue lifecycle ownership in place.

**Acceptance Criteria:**
- `RunController` no longer constructs normalized payloads directly
- issue owner tests pass
- runtime behavior remains unchanged

**Out of Scope:**
- mission owner delegation

#### E2-I5

**Title:** `Delegate mission leaf owners normalized shaping to runtime-core`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Delegate issue owner normalized shaping to runtime-core`

**Summary:**  
Make worker handles and packet executors delegate normalized execution shaping to runtime-core while preserving mission leaf ownership.

**Acceptance Criteria:**
- worker/packet owners no longer shape normalized payloads directly
- mission leaf tests pass

**Out of Scope:**
- round supervision shaping

#### E2-I6

**Title:** `Delegate round supervision shaping to runtime-core`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Delegate mission leaf owners normalized shaping to runtime-core`

**Summary:**  
Move round-level normalized payload shaping behind runtime-core while preserving round lifecycle ownership in `RoundOrchestrator`.

**Acceptance Criteria:**
- round supervision shaping is centralized
- round owner remains intact
- tests confirm round is still supervision, not execution attempt

**Out of Scope:**
- decision-core primitives

#### E2-I7

**Title:** `Migrate consumers to runtime-core facades only`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Delegate round supervision shaping to runtime-core`

**Summary:**  
Ensure downstream consumers use runtime-core facades and no longer branch on owner-local raw file interpretation logic.

**Acceptance Criteria:**
- dashboard/analytics/context/replay use runtime-core seam
- duplicate local interpretation logic removed or reduced to thin adapters

**Out of Scope:**
- decision-core extraction

#### E2-I8

**Title:** `Add runtime-core structural guard tests`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Migrate consumers to runtime-core facades only`

**Summary:**  
Add tests that prevent structural regression back into scattered normalized read/write logic.

**Acceptance Criteria:**
- structural guard tests exist
- test suite fails when normalized shaping leaks back into owners

**Out of Scope:**
- package rename beyond runtime-core

#### E2-I9

**Title:** `Review and freeze runtime-core package boundaries`

**Priority:** `P1`

**Labels:** `arch-extraction`, `runtime-core`

**Depends on:** `Add runtime-core structural guard tests`

**Summary:**  
Perform a package-boundary review so runtime-core extraction ends with an explicit structural checkpoint, not a drifting middle state.

**Acceptance Criteria:**
- package-boundary review completed
- unresolved leaks documented
- go/no-go decision for decision-core extraction recorded

**Out of Scope:**
- decision-core implementation

### Epic 3: Decision Core Extraction

#### E3-I1

**Title:** `Create decision-core package skeleton`

**Priority:** `P0`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Review and freeze runtime-core package boundaries`

**Summary:**  
Create the visible package boundary for decision-core so supervision and intervention primitives stop landing ad hoc in owners and dashboard helpers.

**Acceptance Criteria:**
- `decision_core/` package exists
- import tests pass

**Out of Scope:**
- live mission integration

#### E3-I2

**Title:** `Define decision primitives and initial decision-point inventory`

**Priority:** `P0`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Create decision-core package skeleton`

**Summary:**  
Add the first-class decision vocabulary and classify current decision points into rule-owned, LLM-owned, and human-required categories.

**Acceptance Criteria:**
- `DecisionPoint` exists
- `DecisionRecord` exists
- `Intervention` exists
- initial inventory documented

**Out of Scope:**
- full decision-quality scoring

#### E3-I3

**Title:** `Write mission supervision decisions through decision-core`

**Priority:** `P1`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Define decision primitives and initial decision-point inventory`

**Summary:**  
Make mission round supervision emit first-class decision records through decision-core.

**Acceptance Criteria:**
- supervisor round review emits `DecisionRecord`
- `ask_human` emits intervention data
- round tests pass

**Out of Scope:**
- dashboard review queue migration

#### E3-I4

**Title:** `Move approval queue and approval state derivation behind decision-core`

**Priority:** `P1`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Write mission supervision decisions through decision-core`

**Summary:**  
Make approval queue and review-state derivation consume decision-core rather than ad hoc dashboard helper logic.

**Acceptance Criteria:**
- approval queue uses decision-core state
- dashboard approval tests pass

**Out of Scope:**
- non-mission decision points

#### E3-I5

**Title:** `Expand decision-point inventory to non-mission LLM-controlled branches`

**Priority:** `P1`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Move approval queue and approval state derivation behind decision-core`

**Summary:**  
Extend the inventory to issue-path and non-mission decision points so decision-core is not mission-only.

**Acceptance Criteria:**
- flow/router/reviewer/scoper/conductor-type points classified
- documentation updated

**Out of Scope:**
- memory linkage

#### E3-I6

**Title:** `Add decision review schema for human and self review`

**Priority:** `P1`

**Labels:** `arch-extraction`, `decision-core`

**Depends on:** `Expand decision-point inventory to non-mission LLM-controlled branches`

**Summary:**  
Add the schema for post-hoc decision review so decisions can later be graded, escalated, or promoted based on reviewed evidence.

**Acceptance Criteria:**
- `DecisionReview` exists
- human review fields exist
- self-reflection fields exist
- escalation judgment fields exist

**Out of Scope:**
- memory storage

### Epic 4: Acceptance Judgment and Calibration

#### E4-I1

**Title:** `Define acceptance judgment model`

**Priority:** `P0`

**Labels:** `arch-extraction`, `acceptance-judgment`

**Depends on:** `Decision Core Extraction`

**Summary:**  
Define the canonical judgment model for acceptance, including base run modes, compare overlay, judgment classes, and workflow states.

**Acceptance Criteria:**
- `Acceptance Judgment Model` doc exists
- canonical terms are fixed: `verify / replay / explore / recon`, `confirmed_issue / candidate_finding / observation`, `queued / reviewed / promoted / dismissed / archived`
- `held` is explicitly demoted from ontology to workflow wording

**Out of Scope:**
- production queue implementation
- dashboard-specific fixtures

#### E4-I2

**Title:** `Define acceptance routing policy`

**Priority:** `P0`

**Labels:** `arch-extraction`, `acceptance-judgment`

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

#### E4-I3

**Title:** `Define candidate-finding object model and review SOP`

**Priority:** `P0`

**Labels:** `arch-extraction`, `acceptance-judgment`

**Depends on:** `Define acceptance judgment model`

**Summary:**  
Define the minimum schema and review protocol for uncertain exploratory findings so they can be reviewed, promoted, dismissed, deduped, and archived without being confused with raw observations.

**Acceptance Criteria:**
- `Candidate Findings Review SOP` doc exists
- required fields are defined: `claim`, `surface/route`, `evidence refs`, `confidence`, `impact_if_true`, `repro_status`, `hold_reason`, `promotion_test`, `recommended_next_step`, `dedupe_key`
- queue state transitions are defined

**Out of Scope:**
- compare fixtures

#### E4-I4

**Title:** `Add decision-core-compatible disposition seam`

**Priority:** `P1`

**Labels:** `arch-extraction`, `acceptance-judgment`, `decision-core`

**Depends on:** `Decision Core Extraction`, `Define candidate-finding object model and review SOP`

**Summary:**  
Land the minimum runtime seam so candidate findings and review states plug into `decision_core` rather than inventing a parallel acceptance-owned review object.

**Acceptance Criteria:**
- acceptance disposition objects route through the decision seam
- no duplicate acceptance-only review lifecycle appears in legacy services
- unit tests lock object placement and state transitions

**Out of Scope:**
- dashboard UI work

#### E4-I5

**Title:** `Define dashboard surface pack v1`

**Priority:** `P1`

**Labels:** `arch-extraction`, `acceptance-judgment`, `surface-pack`

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

#### E4-I6

**Title:** `Add comparative calibration harness`

**Priority:** `P1`

**Labels:** `arch-extraction`, `acceptance-judgment`, `calibration`

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

#### E4-I7

**Title:** `Add candidate-to-fixture graduation loop`

**Priority:** `P2`

**Labels:** `arch-extraction`, `acceptance-judgment`, `calibration`

**Depends on:** `Add comparative calibration harness`, `Memory and Learning Linkage`

**Summary:**  
Define how repeated or validated candidate findings graduate into fixture candidates and then into stable regression assets.

**Acceptance Criteria:**
- graduation rules are explicit
- repeated candidate findings can become fixture candidates
- fixture-candidate promotion leaves an audit trail

**Out of Scope:**
- cross-surface scale-out

### Epic 5: Memory and Learning Linkage

#### E5-I1

**Title:** `Ingest normalized execution outcomes into memory`

**Priority:** `P1`

**Labels:** `arch-extraction`, `memory-linkage`

**Depends on:** `Add decision review schema for human and self review`, `Acceptance Judgment and Calibration`

**Summary:**  
Extend memory ingestion so it can consume normalized execution outcomes instead of relying only on legacy report-derived summaries.

**Acceptance Criteria:**
- normalized outcome ingestion exists
- existing memory behavior remains stable

**Out of Scope:**
- decision record ingestion

#### E5-I2

**Title:** `Ingest decision records into memory`

**Priority:** `P1`

**Labels:** `arch-extraction`, `memory-linkage`

**Depends on:** `Ingest normalized execution outcomes into memory`

**Summary:**  
Record decision records into episodic and semantic memory where appropriate so reviewed decision cases become first-class learning inputs.

**Acceptance Criteria:**
- decision records can be stored
- reviewed/unreviewed distinction is preserved

**Out of Scope:**
- evolution promotion

#### E5-I3

**Title:** `Build learning views over reviewed decisions`

**Priority:** `P2`

**Labels:** `arch-extraction`, `memory-linkage`

**Depends on:** `Ingest decision records into memory`

**Summary:**  
Expose reviewed decision failures, success recipes, and intervention histories as structured learning views.

**Acceptance Criteria:**
- decision failure patterns exist
- decision success recipes exist
- intervention history views exist

**Out of Scope:**
- context injection

#### E5-I4

**Title:** `Inject decision-related learnings into context assembly`

**Priority:** `P2`

**Labels:** `arch-extraction`, `memory-linkage`

**Depends on:** `Build learning views over reviewed decisions`

**Summary:**  
Allow planner/reviewer/supervisor/scoper nodes to consume relevant prior decision cases through role-aware context injection.

**Acceptance Criteria:**
- context assembler can inject decision learnings
- role-aware selection exists

**Out of Scope:**
- evolution triggers

#### E5-I5

**Title:** `Add provenance-aware recall for decisions and outcomes`

**Priority:** `P2`

**Labels:** `arch-extraction`, `memory-linkage`

**Depends on:** `Inject decision-related learnings into context assembly`

**Summary:**  
Improve recall so decisions and outcomes carry latest-first and reviewed-vs-unreviewed provenance into downstream context.

**Acceptance Criteria:**
- provenance is exposed in recall results
- latest-first behavior exists

**Out of Scope:**
- promotion policies

### Epic 6: Evolution and Policy Promotion Linkage

#### E6-I1

**Title:** `Make evolution triggers consume normalized execution and decision signals`

**Priority:** `P1`

**Labels:** `arch-extraction`, `evolution-linkage`

**Depends on:** `Add provenance-aware recall for decisions and outcomes`

**Summary:**  
Update evolution triggers so they consume normalized outcome and decision signals rather than only legacy report-derived summaries.

**Acceptance Criteria:**
- evolution trigger path can read normalized signals

**Out of Scope:**
- prompt evolution changes

#### E6-I2

**Title:** `Make prompt evolution consume reviewed decision evidence`

**Priority:** `P2`

**Labels:** `arch-extraction`, `evolution-linkage`

**Depends on:** `Make evolution triggers consume normalized execution and decision signals`

**Summary:**  
Allow prompt evolution inputs to include reviewed decision failures and success cases.

**Acceptance Criteria:**
- prompt evolver can read reviewed decision evidence

**Out of Scope:**
- policy promotion

#### E6-I3

**Title:** `Add promotion review gate for high-impact policy assets`

**Priority:** `P2`

**Labels:** `arch-extraction`, `evolution-linkage`

**Depends on:** `Make prompt evolution consume reviewed decision evidence`

**Summary:**  
Require reviewed evidence before promoting high-impact prompts, skills, or policies.

**Acceptance Criteria:**
- promotion review gate exists
- reviewed evidence requirement is enforceable

**Out of Scope:**
- rollback semantics

#### E6-I4

**Title:** `Add supersession and rollback semantics for promoted assets`

**Priority:** `P2`

**Labels:** `arch-extraction`, `evolution-linkage`

**Depends on:** `Add promotion review gate for high-impact policy assets`

**Summary:**  
Introduce explicit supersession and rollback semantics so policy assets are not append-only forever.

**Acceptance Criteria:**
- promoted assets can be superseded
- rollback path exists

**Out of Scope:**
- analytics over promotion origins

#### E6-I5

**Title:** `Add evolution observability over reviewed decisions and promotions`

**Priority:** `P2`

**Labels:** `arch-extraction`, `evolution-linkage`

**Depends on:** `Add supersession and rollback semantics for promoted assets`

**Summary:**  
Track which promotions came from execution evidence, reviewed decisions, or self-reflection-only evidence.

**Acceptance Criteria:**
- promotion origin observability exists
- reviewed vs unreviewed evidence sources are distinguishable

**Out of Scope:**
- contract extraction

### Epic 7: Contract Core Extraction and Surface Cleanup

#### E7-I1

**Title:** `Create contract-core package skeleton`

**Priority:** `P2`

**Labels:** `arch-extraction`, `contract-core`

**Depends on:** `Add evolution observability over reviewed decisions and promotions`

**Summary:**  
Create the visible package boundary for contract-core so spec snapshot and contract normalization logic have a stable home.

**Acceptance Criteria:**
- `contract_core/` package exists

**Out of Scope:**
- moving all contract behavior immediately

#### E7-I2

**Title:** `Extract contract snapshot and freeze logic behind contract-core`

**Priority:** `P2`

**Labels:** `arch-extraction`, `contract-core`

**Depends on:** `Create contract-core package skeleton`

**Summary:**  
Move snapshot/freeze semantics toward contract-core while preserving runtime behavior.

**Acceptance Criteria:**
- snapshot/freeze logic has contract-core seam

**Out of Scope:**
- spec importers

#### E7-I3

**Title:** `Extract spec question and decision recording behind contract-core`

**Priority:** `P2`

**Labels:** `arch-extraction`, `contract-core`

**Depends on:** `Extract contract snapshot and freeze logic behind contract-core`

**Summary:**  
Stop treating CLI pathways as the natural home of contract decision recording.

**Acceptance Criteria:**
- question/decision recording has contract-core seam

**Out of Scope:**
- surface cleanup

#### E7-I4

**Title:** `Move spec import and normalization behind contract-core`

**Priority:** `P2`

**Labels:** `arch-extraction`, `contract-core`

**Depends on:** `Extract spec question and decision recording behind contract-core`

**Summary:**  
Make spec importers and normalization a contract-core concern rather than an isolated import utility.

**Acceptance Criteria:**
- spec import path has contract-core seam

**Out of Scope:**
- dashboard cleanup

#### E7-I5

**Title:** `Run surface cleanup pass across CLI, daemon, and dashboard`

**Priority:** `P2`

**Labels:** `arch-extraction`, `surface-cleanup`

**Depends on:** `Move spec import and normalization behind contract-core`

**Summary:**  
Thin the major surfaces so they consume core seams more consistently and stop encoding core business truth directly.

**Acceptance Criteria:**
- CLI/dashboard/daemon surface cleanup pass completed
- major cross-core leaks documented or removed

**Out of Scope:**
- new core creation

---

## 5. Suggested Linear Creation Order

Create in this order:

1. Create all 7 Epics
2. Create all Epic 1 issues
3. Create all Epic 2 issues
4. Create all Epic 3 issues
5. Create all Epic 4 issues
6. Create all Epic 5 issues
7. Create all Epic 6 issues
8. Create all Epic 7 issues

If time is limited, at minimum create:

- all 7 Epics
- Epic 1 issues
- Epic 2 issues
- Epic 3 issues
- Epic 4 issues

because those are the current execution horizon.

---

## 6. What Remains After This

After this document, the remaining work is no longer architecture design.

It is operational:

1. create or update these Epics in Linear
2. create or update these Issues in Linear
3. attach owners / estimates / cycle targets
4. start with Epic 1 issue 1
