# Release Acceptance History and Archive Program

> **Date:** 2026-04-02
> **Status:** archive contract lock
> **Purpose:** make each formal acceptance pass a durable, queryable release
> bundle so future dashboard/workbench/showcase surfaces can render historical
> runs, findings, fixes, and reruns without reconstructing state from ad hoc
> filesystem scans

## 1. Why This Exists

Acceptance is no longer just a local smoke script.

It is now part of the product workflow:

1. run formal acceptance
2. classify `harness_bug` / `n2n_bug` / `ux_gap`
3. fix the right thing
4. rerun
5. compare to the previous `source_run`
6. freeze the baseline

If this lifecycle is going to become operator-visible later, every formal
acceptance version needs a durable bundle, not just scattered JSON files.

This program defines that durable bundle.

## 2. Relationship to the Current 7-Epic Program

This work should **not** be buried under a single existing epic.

It spans:

- `SON-370` Shared Operator Semantics
- `SON-374` Runtime and Execution Substrate
- `SON-379` Decision and Judgment Substrate
- `SON-390` Judgment Workbench v1
- `SON-396` Learning Workbench v1

And it also feeds downstream narrative/showcase work such as `SON-363`.

So the right placement is:

- a **small standalone archive program**
- explicitly downstream of acceptance/report stabilization
- explicitly upstream of workbench history surfaces and showcase/timeline views

In other words:

- it does **not** replace the 7-epic program
- it provides the historical data layer those epics will consume

### Linear Placement

This program is now tracked as a standalone sidecar epic in Linear:

- `SON-419` `[Epic] Release Acceptance History and Archive`
- `SON-420` Define release acceptance bundle schema and archive directory contract
- `SON-421` Add rolling release acceptance index and artifact manifest writer
- `SON-422` Record finding lifecycle lineage across acceptance reruns
- `SON-423` Seed the first archived acceptance baseline bundle
- `SON-424` Expose archive read models for future judgment, learning, and showcase surfaces

This placement is intentional:

- it stays downstream of acceptance/report stabilization
- it stays upstream of `SON-390`, `SON-396`, and `SON-363`
- it remains cross-cutting without trying to redefine any single workbench epic

## 3. What Counts as a Formal Acceptance Version

A formal acceptance version is a named bundle produced only when the canonical
acceptance suite has been run and status has been refreshed.

For now the required suite is:

- `issue_start_smoke --full`
- `mission_start_acceptance --full`
- `dashboard_ui_acceptance --full`
- `exploratory_acceptance_smoke --full`
- consolidated `stability_acceptance_status`

Only after those have been materialized should a release acceptance bundle be
written.

## 4. Canonical Archive Root

Archive history should live under:

```text
docs/acceptance-history/
```

This is intentionally dashboard-readable and repo-local.

Within it:

```text
docs/acceptance-history/
  index.json
  releases/
    <release_id>/
      manifest.json
      summary.md
      status.json
      findings.json
      source_runs.json
      artifacts.json
```

## 5. Release Bundle Contract

Every release bundle should contain the same top-level fields.

### 5.1 `manifest.json`

Required fields:

- `release_id`
- `release_label`
- `created_at`
- `git_commit`
- `git_branch`
- `acceptance_suite_version`
- `overall_status`
- `checks`
- `source_runs`
- `artifacts`
- `lineage`

### 5.2 `status.json`

The normalized operator-facing summary:

- `overall_status`
- `reported_checks`
- `checks`
- `frozen`

### 5.3 `findings.json`

All normalized findings/proposals across the bundle:

- `finding_id`
- `bug_type`
- `severity`
- `confidence`
- `summary`
- `route`
- `operator_task`
- `why_it_matters`
- `recommended_fix`
- `source_run`
- `current_state`

### 5.4 `source_runs.json`

The exact run provenance used to build the release bundle:

- `issue_start`
- `mission_start`
- `dashboard_ui`
- `exploratory`

Each source run should preserve:

- `mission_id` or `issue_id`
- `round_id`
- `report_path`
- `runtime_chain_root`

### 5.5 `artifacts.json`

Artifact index for future UI consumers:

- `status_markdown`
- `status_json`
- per-check report paths
- screenshot roots
- browser evidence paths
- runtime chain roots

## 6. History Index Contract

`docs/acceptance-history/index.json` should remain small and append-only.

Each entry should contain:

- `release_id`
- `release_label`
- `created_at`
- `git_commit`
- `overall_status`
- `findings_count`
- `issue_proposal_count`
- `bundle_path`

This is the first file future dashboard/showcase surfaces should read.

## 7. Finding Lifecycle Lineage

The archive should not only store final results.
It should store problem lineage.

Each finding should eventually be able to express:

- `introduced_by_run`
- `fixed_by_commit`
- `verified_by_run`
- `regressed_by_run`
- `current_state`

Current accepted states:

- `open`
- `verified_fixed`
- `regressed`
- `held_for_review`
- `archived`

This is the seam that later feeds:

- Judgment timeline
- Learning timeline
- Showcase narrative

## 8. Relationship to Workbench Surfaces

### 8.1 Judgment Workbench

Consumes:

- release status
- source runs
- findings
- finding lineage

### 8.2 Learning Workbench

Consumes:

- repeated findings across releases
- verified fixes
- regressions
- promoted patterns

### 8.3 Showcase / Narrative Layer

Consumes:

- release index
- timeline of bundles
- before/after rerun evidence
- top-level summaries and artifact entry points

## 9. Initial Implementation Scope

The initial tranche should do four things only:

1. define the release bundle schema
2. define the archive root and history index
3. seed the current acceptance-freeze baseline as the first bundle
4. update the formal acceptance workflow so future versions always write a
   bundle

Do **not** block on:

- final dashboard UI
- final showcase UI
- final learning promotion logic

## 10. Recommended Linear Shape

Create one new sidecar epic:

- `Release Acceptance History and Archive`

Child work should cover:

1. define the release acceptance bundle schema
2. add archive writer + rolling index
3. record finding lifecycle lineage
4. seed the first formal baseline bundle
5. expose archive read models for future dashboard/showcase consumption

## 11. Initial Release Seed

The current baseline should be treated as the first official archive seed:

- `release_id = acceptance-freeze-baseline-2026-04-02`
- `overall_status = pass`
- `reported_checks = 4/4`

This first bundle proves the archive contract before the workbench UI exists.
