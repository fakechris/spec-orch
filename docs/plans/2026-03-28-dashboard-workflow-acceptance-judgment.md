# Dashboard Workflow Acceptance Judgment

## Goal

Record the current state of dashboard workflow acceptance after `SON-257`.

This document is intentionally conservative. It distinguishes:

- capabilities already proven by real workflow dogfood replay
- capabilities that are only partially exercised or only instrumented
- capabilities that are still outside the current workflow acceptance contract

It is meant to prevent over-claiming what the harness can do today.

## Evidence Base

Current judgment is based on:

- workflow replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260328T233202Z/acceptance_review.json`
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260328T233202Z/browser_evidence.json`
- launcher mutation replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T004922Z-launcher-mutation/browser_evidence.json`
- launcher launch replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T010347Z-launcher-launch/browser_evidence.json`
- approval action replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T010209Z-approval-replay/browser_evidence.json`
- transcript/context replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T013209Z-root-transcript-context-replay/browser_evidence.json`
- secondary action replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T013623Z-secondary-actions-replay/browser_evidence.json`
- launcher Linear mutation replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T014609Z-linear-create-bind-replay/browser_evidence.json`
- cost review route replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T014657Z-cost-review-route-replay/browser_evidence.json`
- inbox triage replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T020500Z-inbox-replay/browser_evidence.json`
- approval queue batch replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T020700Z-approval-queue-batch-replay/browser_evidence.json`
- highest-cost packet replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T021300Z-highest-cost-packet-replay/browser_evidence.json`
- budget incident replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T032000Z-budget-incident-replay/browser_evidence.json`
- approval revision replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T034500Z-approval-revision-replay/browser_evidence.json`
- approval follow-up replay artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T034700Z-approval-followup-replay/browser_evidence.json`
- consolidated dashboard coverage sweep artifact:
  - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260329T041500Z-dashboard-coverage-sweep/browser_evidence.json`
- contract and route planning:
  - `src/spec_orch/services/round_orchestrator.py`
- dashboard semantics:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
- operator surface inventory:
  - `docs/guides/operator-console.md`

## Current Verdict

Current workflow acceptance state:

- `status: pass`
- `coverage_status: complete`
- `confidence: 0.97`
- `tested_routes: 6` in the latest consolidated same-version sweep
- `findings: 0`
- `issue_proposals: 0`

The current replay proves that the dashboard can now sustain a real, non-trivial operator workflow replay without browser errors, empty-shell findings, or unstable text-only selectors. The latest same-version sweep also re-validated launcher Linear mutations, root/mode selection, mission-detail tabbing, transcript drill-down, budget incident routing, visual QA transcript jumps, and both approval action variants with zero page errors and zero console errors.

This judgment now explicitly covers `Workflow Replay E2E`, not `Fresh Acpx Mission E2E`.
The dashboard has been exercised against live browser routes, real operator actions, and real launcher mutations, but not yet against a brand-new mission that is freshly executed by a new `acpx` builder run.

## Proven Capabilities

The following capabilities are now proven by real browser replay, not only unit tests:

1. The launcher can be opened from the dashboard header.
2. The launcher readiness refresh action can be executed and return a success state.
3. Mission Control can switch into `Needs Attention`.
4. Mission Control can switch into `All Missions`.
5. Mission Control can switch into `Decision Queue`.
6. Mission Control can switch into `Deep Evidence`.
7. A target mission can be selected from the mission list using stable automation semantics.
8. Mission detail can reach a stable loaded state after mission selection.
9. The `Overview` tab is reachable and restorable.
10. The `Transcript` tab is reachable.
11. The `Approvals` tab is reachable.
12. The `Visual QA` tab is reachable.
13. The `Acceptance` tab is reachable.
14. The `Costs` tab is reachable.
15. The workflow replay can complete end-to-end with selector-based assertions and no page errors.
16. The launcher can create a mission draft through real browser mutation.
17. The launcher can approve and plan that draft through real browser mutation.
18. The launcher can launch an already planned local mission through real browser mutation.
19. Approval action execution can apply `approve` through the real dashboard endpoint.
20. Approval action execution records operator history in `approval_actions.jsonl`.
21. Approval action execution records BTW context in `.spec_orch_runs/<issue>/btw_context.md`.
22. Packet selection can switch the active packet in Overview using stable selectors.
23. Transcript filters can switch the transcript view to `message` and hold an active state.
24. Transcript block inspection can activate a specific transcript block through real replay.
25. At least one context-rail internal action link can navigate into the Acceptance review surface.
26. The secondary `Discuss` action can open the mission discussion pane.
27. The secondary `Refresh` action can reload mission detail while preserving a stable loaded state.
28. The launcher can create a real Linear issue through browser replay.
29. The launcher can bind an existing Linear issue to a mission through browser replay.
30. A second context-rail route variant can navigate into the Costs review surface.
31. Inbox triage can open a live attention item and load mission detail from the Needs Attention surface.
32. The approval queue can batch-apply `approve` through the real dashboard endpoint.
33. Approval queue batch execution can drive a pending mission into `approval_granted`.
34. A costs-panel route variant can jump directly into the highest-cost packet transcript.
35. The approval workspace can apply `request_revision` and settle on `revision_requested` through real replay.
36. The approval workspace can apply `ask_followup` and settle on `followup_requested` through real replay.
37. Visual QA can render diff-first evidence and jump into a focused packet transcript through real replay.
38. Inbox budget triage can land on the Costs surface and jump into the expensive packet transcript through real replay.

This means the current system has already proven a full `workflow acceptance` loop for the core non-destructive dashboard navigation path.

## Unproven Capabilities

The following are **not** yet proven by the current workflow replay:

1. Fresh mission full E2E:
   - create
   - approve/plan
   - bind Linear
   - launch
   - daemon pickup
   - post-launch workflow acceptance

These are not failures. They are simply outside the currently proven workflow contract.

## Coverage Matrix

Coverage here is capability-based, not DOM-element-based.

### A. Core Workflow Navigation Coverage

This is the narrowest and most important metric for `SON-257`.

| Capability | Status |
|---|---|
| Open launcher | Proven |
| Refresh launcher readiness | Proven |
| Switch to Needs Attention | Proven |
| Switch to All Missions | Proven |
| Switch to Decision Queue | Proven |
| Switch to Deep Evidence | Proven |
| Select mission from mission list | Proven |
| Overview tab | Proven |
| Transcript tab | Proven |
| Approvals tab | Proven |
| Visual QA tab | Proven |
| Acceptance tab | Proven |
| Costs tab | Proven |

Result:

- `13 / 13` core workflow navigation capabilities proven
- `100%` of the current non-destructive workflow-navigation contract is covered by real replay

### B. Broader Dashboard Capability Coverage

This is the more honest product-surface metric.

| Capability Group | Status |
|---|---|
| Launcher open | Proven |
| Launcher readiness refresh | Proven |
| Launcher create draft | Proven |
| Launcher approve & plan | Proven |
| Launcher create Linear issue | Proven |
| Launcher bind existing Linear issue | Proven |
| Launcher launch mission | Proven |
| Mission control mode switching | Proven |
| Inbox triage interaction | Proven |
| Approval queue batch action | Proven |
| Mission selection | Proven |
| Overview | Proven |
| Transcript surface | Proven |
| Transcript filters / inspector | Proven |
| Approvals surface reachability | Proven |
| Approval action execution | Proven |
| Visual QA surface reachability | Proven |
| Visual QA interactive evidence inspection | Proven |
| Acceptance surface reachability | Proven |
| Costs surface reachability | Proven |
| Budget incident routing / escalation drill-down | Proven |
| Packet selection workflow | Proven |
| Context rail action links | Proven (acceptance-review jump) |
| Highest-cost packet jump | Proven |
| Discuss / refresh secondary actions | Proven |
| Approval revision variant | Proven |
| Approval follow-up variant | Proven |

Result:

- `25 / 25` broader dashboard capabilities proven by workflow replay
- `100%` of the currently scoped dashboard workflow-replay capability inventory is covered

This is the more useful number when asking, "How much of the dashboard is really under end-to-end workflow acceptance today?"

## What This Means

We can now make a strong claim:

- workflow acceptance for the dashboard is real
- it is not a text-click demo anymore
- it already supports one full detect → fix → replay confirmation loop
- the remaining gap is now pipeline freshness, not dashboard workflow operability

But we should **not** yet claim:

- the dashboard is comprehensively covered end-to-end
- live budget-incident action flows are proven
- a fresh mission full lifecycle is proven
- exploratory user-perspective critique is proven

## What Was Already Iterated Through Feedback

The quality loop has already produced real fixes:

1. The earlier root-route page error (`Unexpected end of input`) was reproduced by replay and fixed.
2. Empty-shell acceptance findings were normalized or discarded so that replay output became actionable.
3. Workflow replay exposed unstable mission-selection success semantics on the root route.
4. Stable `mission-detail-ready` semantics were added, and replay was rerun until the workflow passed cleanly.
5. Approval replay exposed malformed inline `onclick` handlers for `safeJsArg(...)` helper buttons.
6. Those handlers were repaired, and replay then verified that `approve` reached the real dashboard endpoint and changed approval state.
7. Transcript/context replay exposed that `renderInternalRouteButton()` existed but was not exported from the helper bundle.
8. The helper export was restored, and replay then verified packet selection, transcript filtering, transcript-block activation, and an acceptance review context-rail jump.
9. Secondary `Discuss / Refresh` actions were given stable automation semantics and replay then verified both actions through the live dashboard.
10. Launcher readiness under-reported Linear availability because the dashboard only recognized `SPEC_ORCH_LINEAR_TOKEN`; fallback support for `LINEAR_TOKEN` / `LINEAR_API_TOKEN` was added and then verified through real `linear-create` and `linear-bind` replay.
11. Inbox replay now verifies that a live attention item can open mission detail from the Needs Attention surface.
12. Approval queue replay exposed malformed approval-selection inline handlers; those handlers were repaired and replay then verified real batch approval through the queue toolbar.
13. A stable transcript-inspector automation target was added so a costs-panel replay could prove the highest-cost packet jump reached the intended transcript context.

This is important: the harness is no longer just surfacing observations. It has already driven concrete dashboard fixes and then re-validated them.

## Next Validation Targets

The next best validation steps should stay inside the dashboard before expanding into `Exploratory Acceptance`.

Priority order:

1. Prove follow-up / revision approval variants when present.
2. Prove a visual QA gallery / diff interaction when live evidence is present.
3. Prove a cost escalation or budget incident action flow when data is present.
4. Run one fresh mission full lifecycle dogfood:
   - create
   - approve & plan
   - bind Linear
   - launch
   - daemon pickup
   - workflow acceptance replay after launch

## Recommendation

Do not open a PR yet for this quality pass until at least one of the following is also proven by replay:

- live budget-incident action flow
- inbox triage interaction flow
- fresh mission full lifecycle

Reason:

`SON-257` is already functionally complete and proven for the core workflow-navigation contract, and the richer dashboard story is now at `25 / 25` currently scoped workflow-replay capabilities. The next increment should move into `Fresh Acpx Mission E2E` rather than opening a PR that still conflates workflow replay coverage with fresh pipeline execution.
