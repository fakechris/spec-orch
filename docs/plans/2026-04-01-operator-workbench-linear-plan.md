# Operator Workbench Linear Plan

> **Date:** 2026-04-01
> **Status:** Linear-ready
> **Source:** `2026-04-01-operator-workbench-program-plan.md`
> **Team:** `SON`

## 0. Created Linear IDs

- `SON-370` `[Epic] Shared Operator Semantics`
- `SON-371` `Define shared operator identity and status carriers`
- `SON-372` `Define shared operator event and artifact envelopes`
- `SON-373` `Define intervention and audit carriers`
- `SON-374` `[Epic] Runtime and Execution Substrate`
- `SON-375` `Add runtime registry and health model for operator surfaces`
- `SON-376` `Add active work and queue state carriers`
- `SON-377` `Add execution event trail and progress summary seam`
- `SON-378` `Add auditable operator intervention hooks`
- `SON-379` `[Epic] Decision and Judgment Substrate`
- `SON-380` `Finalize acceptance routing policy as canonical decision input`
- `SON-381` `Finalize candidate finding and observation provenance model`
- `SON-382` `Add disposition and review state carriers for dashboard consumption`
- `SON-383` `Add compare overlay and baseline drift carriers`
- `SON-384` `[Epic] Execution Workbench v1`
- `SON-385` `Build Agents surface`
- `SON-386` `Build Runtimes surface`
- `SON-387` `Build Active Work surface`
- `SON-388` `Add live execution panels to mission and issue views`
- `SON-389` `Add operator action controls and audit recap`
- `SON-390` `[Epic] Judgment Workbench v1`
- `SON-391` `Build Evidence Bundle surface`
- `SON-392` `Build Judgment Timeline surface`
- `SON-393` `Build Candidate Findings review surface`
- `SON-394` `Build compare overlay surface`
- `SON-395` `Land dashboard surface pack v1 in workbench form`
- `SON-396` `[Epic] Learning Workbench v1`
- `SON-397` `Add reviewed finding to memory linkage`
- `SON-398` `Add candidate-to-fixture graduation registry`
- `SON-399` `Build repeated-pattern analytics surface`
- `SON-400` `Build learning timeline surface`
- `SON-401` `Expose policy promotion and rollback history`
- `SON-402` `[Epic] Surface Cleanup and Workbench Cutover`
- `SON-403` `Move legacy execution reads onto canonical workbench seams`
- `SON-404` `Move legacy acceptance reads onto canonical judgment seams`
- `SON-405` `Thin legacy mission detail surfaces after workbench cutover`
- `SON-406` `Document operator workflows and cutover rules`

## 1. Epic Cards

### Epic 1

**Title:** `[Epic] Shared Operator Semantics`

**Summary:**  
Create the shared operator-facing vocabulary used by execution, judgment, and
learning surfaces. Normalize identity, status, event, artifact, and audit
carriers so later workbenches consume one language instead of inventing
dashboard-local semantics.

### Epic 2

**Title:** `[Epic] Runtime and Execution Substrate`

**Summary:**  
Strengthen the runtime substrate required for an operator-grade execution
workbench: runtime registry, health, queue state, active-work state, heartbeat,
and intervention seams.

### Epic 3

**Title:** `[Epic] Decision and Judgment Substrate`

**Summary:**  
Strengthen routing, disposition, review, candidate-finding provenance, compare
overlay semantics, and dashboard-consumable judgment carriers on top of
`decision_core` and `acceptance_core`.

### Epic 4

**Title:** `[Epic] Execution Workbench v1`

**Summary:**  
Build the visible execution workbench for operators: Agents, Runtimes, Active
Work, live execution panels, and intervention controls over canonical runtime
truth.

### Epic 5

**Title:** `[Epic] Judgment Workbench v1`

**Summary:**  
Build the visible judgment workbench for operators: evidence bundles, judgment
timeline, candidate-finding review, compare overlay, and the first calibrated
surface pack.

### Epic 6

**Title:** `[Epic] Learning Workbench v1`

**Summary:**  
Build the visible learning workbench over memory and evolution seams: repeated
patterns, fixture graduation, learning timeline, and promotion / rollback
history.

### Epic 7

**Title:** `[Epic] Surface Cleanup and Workbench Cutover`

**Summary:**  
Remove legacy overlap, move read paths to canonical seams, and thin old pages
once the new execution, judgment, and learning workbenches are stable.

## 2. Issue Cards

### Epic 1: Shared Operator Semantics

#### I1
**Title:** `Define shared operator identity and status carriers`

**Summary:**  
Define canonical identity and status models for agents, runtimes, active work,
judgments, and promoted learnings.

#### I2
**Title:** `Define shared operator event and artifact envelopes`

**Summary:**  
Normalize the event and artifact carriers consumed by workbench surfaces so
execution trails, evidence bundles, and learning timelines speak one common
format.

#### I3
**Title:** `Define intervention and audit carriers`

**Summary:**  
Standardize operator intervention records and audit events so retry, cancel,
reassign, takeover, review, promotion, and rollback actions are traceable
across workbenches.

### Epic 2: Runtime and Execution Substrate

#### I1
**Title:** `Add runtime registry and health model for operator surfaces`

**Summary:**  
Expose runtime identity, health, heartbeat, mode, usage, and recent error
status as canonical runtime-side read models.

#### I2
**Title:** `Add active work and queue state carriers`

**Summary:**  
Expose active work, queue position, claim state, and execution ownership as
canonical read models for operators.

#### I3
**Title:** `Add execution event trail and progress summary seam`

**Summary:**  
Add a canonical execution event trail and compact progress summaries for live
operator inspection.

#### I4
**Title:** `Add auditable operator intervention hooks`

**Summary:**  
Provide canonical hooks and records for retry, cancel, reassign, and takeover
actions.

### Epic 3: Decision and Judgment Substrate

#### I1
**Title:** `Finalize acceptance routing policy as canonical decision input`

**Summary:**  
Promote routing policy into a canonical decision substrate input for verify,
replay, explore, recon, graph profile, and compare overlay activation.

#### I2
**Title:** `Finalize candidate finding and observation provenance model`

**Summary:**  
Finalize canonical provenance fields for confirmed issues, candidate findings,
and observations across evidence and compare flows.

#### I3
**Title:** `Add disposition and review state carriers for dashboard consumption`

**Summary:**  
Add canonical review/disposition carriers so dashboard surfaces can render
judgment state without inventing page-local semantics.

#### I4
**Title:** `Add compare overlay and baseline drift carriers`

**Summary:**  
Expose compare overlay metadata and baseline drift summaries as canonical
judgment-side objects.

### Epic 4: Execution Workbench v1

#### I1
**Title:** `Build Agents surface`

**Summary:**  
Add an operator-facing Agents page that shows ownership, recent work, runtime
binding, and status at a glance.

#### I2
**Title:** `Build Runtimes surface`

**Summary:**  
Add an operator-facing Runtimes page with health, heartbeat, usage, activity,
and mode visibility.

#### I3
**Title:** `Build Active Work surface`

**Summary:**  
Add an Active Work page that shows what is running now, who owns it, where it
is blocked, and which intervention is possible.

#### I4
**Title:** `Add live execution panels to mission and issue views`

**Summary:**  
Embed live execution state into mission and issue detail surfaces so operators
can inspect progress without leaving context.

#### I5
**Title:** `Add operator action controls and audit recap`

**Summary:**  
Expose retry, cancel, reassign, and takeover actions with explicit audit
recaps.

### Epic 5: Judgment Workbench v1

#### I1
**Title:** `Build Evidence Bundle surface`

**Summary:**  
Add a first-class evidence bundle view that unifies transcript, screenshots,
browser evidence, review artifacts, and linked execution context.

#### I2
**Title:** `Build Judgment Timeline surface`

**Summary:**  
Expose the judgment path over time: mode selection, evidence availability,
rationale, confidence, and current disposition.

#### I3
**Title:** `Build Candidate Findings review surface`

**Summary:**  
Add an operator-facing candidate-finding queue and detail view with promotion
tests, next steps, and review outcomes.

#### I4
**Title:** `Build compare overlay surface`

**Summary:**  
Expose baseline/current judgment drift and selected artifact drift through a
dedicated compare surface.

#### I5
**Title:** `Land dashboard surface pack v1 in workbench form`

**Summary:**  
Turn the first calibrated dashboard surface pack into a visible operator
workbench surface rather than a hidden evaluator concept.

### Epic 6: Learning Workbench v1

#### I1
**Title:** `Add reviewed finding to memory linkage`

**Summary:**  
Make reviewed findings visible as memory-linked learning assets with explicit
provenance.

#### I2
**Title:** `Add candidate-to-fixture graduation registry`

**Summary:**  
Track and expose when repeated reviewed findings graduate into fixture
candidates and regression assets.

#### I3
**Title:** `Build repeated-pattern analytics surface`

**Summary:**  
Add operator-visible repeated-pattern analytics across findings, failures,
degraded paths, and promoted recipes.

#### I4
**Title:** `Build learning timeline surface`

**Summary:**  
Expose learning events, promotions, dismissals, memory updates, and evolution
proposals as one operator-visible timeline.

#### I5
**Title:** `Expose policy promotion and rollback history`

**Summary:**  
Make the origin, approval, supersession, and rollback status of promoted policy
and evolution assets visible.

### Epic 7: Surface Cleanup and Workbench Cutover

#### I1
**Title:** `Move legacy execution reads onto canonical workbench seams`

**Summary:**  
Replace remaining page-local execution reads with canonical runtime and
operator-semantic carriers.

#### I2
**Title:** `Move legacy acceptance reads onto canonical judgment seams`

**Summary:**  
Replace remaining acceptance-page special cases with workbench-grade judgment
carriers and surfaces.

#### I3
**Title:** `Thin legacy mission detail surfaces after workbench cutover`

**Summary:**  
Remove legacy duplication once execution and judgment workbenches are the
authoritative operator surfaces.

#### I4
**Title:** `Document operator workflows and cutover rules`

**Summary:**  
Update docs and playbooks so operators know when to use execution, judgment,
and learning workbenches and which surfaces are canonical after cutover.
