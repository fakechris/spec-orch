# Stability Acceptance Matrix

**Date:** 2026-03-30  
**Status:** Canonical matrix established; automation coverage still in progress
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
| Feature | Issue-start pipeline smoke | `spec-orch run --source fixture` and targeted unit/integration coverage | run workspace artifacts, normalized execution payloads | Planned |
| Feature | Mission/milestone-start launch | `tests/e2e/fresh_acpx_mission_smoke.sh` family | mission rounds, acceptance review, launch metadata | Planned |
| Feature | Linear-bound mission launch | `tests/e2e/fresh_acpx_mission_smoke.sh` linear-bound variant | `linear_issue.json`, launch metadata, mission run artifacts | Planned |
| UI | Dashboard root and control surfaces | dashboard API/unit suite | API payloads, route readiness, control overview | Partially automated |
| UI | Mission detail / transcript / acceptance review surfaces | dashboard API/unit suite + post-run replay checks | mission detail payload, transcript data, graph artifacts | Partially automated |
| UI | Approval / intervention flows | dashboard approvals and API tests | intervention queue, intervention responses, decision review state | Automated |
| Acceptance | Acceptance routing and judgment semantics | unit suites under `tests/unit/test_acceptance_core_*` | routing decisions, judgment objects, calibration comparisons | Automated |
| Acceptance | Bounded graph runtime | unit suites under `tests/unit/test_acceptance_runtime_*` | graph run, step artifacts, transitions | Automated |
| Acceptance | Graph trace to fixture seed chain | round orchestrator + calibration tests | graduation history, fixture candidate seed JSON | Automated |
| Exploratory | Post-run exploratory acceptance smoke | fresh ACPX/post-run scripts | acceptance review, browser evidence, graph artifacts | Planned |
| Evolution | Reviewed evidence drives evolvers | Epic 6 unit suites | signal bridge, promotion registry, evolution journal | Automated |
| Contract | Contract/snapshot/decision/import seams | Epic 7 unit suites | snapshots, decisions, import results | Automated |

## 4. Immediate Gaps

The first gaps to close are:

1. issue-start e2e needs a canonical smoke harness
2. mission/milestone-start needs a canonical acceptance command and result contract
3. dashboard/UI acceptance needs a single rerunnable harness rather than only scattered unit tests
4. exploratory acceptance should produce stable smoke artifacts suitable for repeated operator review

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
