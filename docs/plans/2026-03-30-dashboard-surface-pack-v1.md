# Dashboard Surface Pack v1

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Implemented baseline

## Goal

Define the first surface-specific acceptance pack for the operator console
without introducing a dashboard-only judgment system.

## Boundary

This pack is surface-specific. It rides on top of:

- `acceptance_core` for judgment/routing/calibration primitives
- `decision_core` for generic review/disposition carriers

It does not define a new parallel queue or lifecycle model.

## Pack Key

`dashboard_surface_pack_v1`

## Subject

- `subject_kind = mission`
- `subject_id = <mission_id>`

## Critique Axes

- `evidence_discoverability`
- `surface_orientation`
- `task_continuity`
- `operator_comprehension`

## Seed Routes

- `/`
- `/?mission=<mission_id>&mode=missions&tab=overview`

## Safe-Action Budget

`bounded`

Meaning:

- do not mutate production-like state casually
- stay within review/navigation interactions by default
- prefer route coverage and evidence collection over broad action branching

## Fixture Set

- `feature_scoped_launcher_regression`
- `workflow_dashboard_repair_loop`
- `exploratory_dashboard_ux_hold`
- `exploratory_dashboard_orientation_hold`
- `dogfood_dashboard_regression`

## Baseline Evidence Shape

- `acceptance_review`
- `browser_evidence`
- `visual_gallery`
- `round_summary`

## Gold Judgment Classes

- `confirmed_issue`
- `candidate_finding`
- `observation`

## Current Code Owner

Canonical code lives in:

- `src/spec_orch/acceptance_core/calibration.py`

Thin consumers currently exist in:

- `src/spec_orch/services/round_orchestrator.py`
- `src/spec_orch/dashboard/launcher.py`
- `src/spec_orch/dashboard/surfaces.py`
