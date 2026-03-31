# Stability Acceptance Matrix

**Date:** 2026-03-30  
**Status:** Canonical matrix established; feature/UI/exploratory baseline harnesses landed
**Parent plan:** [`2026-03-30-program-reconciliation-and-stability-acceptance.md`](./2026-03-30-program-reconciliation-and-stability-acceptance.md)

## 1. Purpose

This matrix defines the minimum acceptance surface that must remain healthy
after the architecture refactor.

The point is not just “run tests.” The point is to prove that spec-orch can:

- start from issue-driven entry points
- start from milestone/mission-driven entry points
- render and operate its main dashboard surfaces
- run acceptance/exploration loops without silently breaking

## 2. Coverage Model

Each row should eventually have:

- a repeatable command
- a durable pass/fail artifact
- a current status
- a linked Linear issue if automation is missing or unstable

## 3. Matrix

| Area | Scenario | Current Harness | Expected Artifact | Status |
|---|---|---|---|---|
| Feature | Issue-start pipeline smoke | `tests/e2e/issue_start_smoke.sh --full` | `.spec_orch/acceptance/issue_start_smoke.json`, run workspace artifacts, normalized execution payloads | Automated |
| Feature | Mission/milestone-start launch | `tests/e2e/mission_start_acceptance.sh --full` | `mission_start_acceptance.json`, mission rounds, acceptance review, launch metadata | Automated |
| Feature | Linear-bound mission launch | `tests/e2e/fresh_acpx_mission_smoke.sh` linear-bound variant | `linear_issue.json`, launch metadata, mission run artifacts | Planned |
| UI | Dashboard root and control surfaces | `tests/e2e/dashboard_ui_acceptance.sh --full` | `.spec_orch/acceptance/dashboard_ui_acceptance.json`, route readiness, control overview | Automated |
| UI | Mission detail / transcript / acceptance review surfaces | `tests/e2e/dashboard_ui_acceptance.sh --full` | `.spec_orch/acceptance/dashboard_ui_acceptance.json`, mission detail payload, transcript data, graph artifacts | Automated |
| UI | Approval / intervention flows | dashboard approvals and API tests | intervention queue, intervention responses, decision review state | Automated |
| Acceptance | Acceptance routing and judgment semantics | unit suites under `tests/unit/test_acceptance_core_*` | routing decisions, judgment objects, calibration comparisons | Automated |
| Acceptance | Bounded graph runtime | unit suites under `tests/unit/test_acceptance_runtime_*` | graph run, step artifacts, transitions | Automated |
| Acceptance | Graph trace to fixture seed chain | round orchestrator + calibration tests | graduation history, fixture candidate seed JSON | Automated |
| Exploratory | Post-run exploratory acceptance smoke | `tests/e2e/exploratory_acceptance_smoke.sh --full` | `exploratory_acceptance_smoke.json`, acceptance review, browser evidence, graph artifacts | Automated |
| Evolution | Reviewed evidence drives evolvers | Epic 6 unit suites | signal bridge, promotion registry, evolution journal | Automated |
| Contract | Contract/snapshot/decision/import seams | Epic 7 unit suites | snapshots, decisions, import results | Automated |

## 4. Immediate Gaps

The next gaps to close are:

1. linear-bound mission launch still needs a canonical automation wrapper
2. dashboard/UI acceptance should eventually gain browser-backed replay in addition to API assertions
3. exploratory acceptance should eventually support non-fresh reruns against preserved missions
4. consolidated status should eventually publish the latest full-run timestamps per harness

## 5. Status Semantics

- `Automated`
  - repeatable command exists and is stable enough for routine reruns
- `Partially automated`
  - key assertions exist, but coverage is fragmented or incomplete
- `Planned`
  - scenario is known and required, but the acceptance harness is not yet the canonical path

## 6. Update Rule

This matrix must be updated whenever:

- a new canonical acceptance harness is added
- a scenario moves from manual/planned to automated
- a major regression invalidates an existing acceptance path
