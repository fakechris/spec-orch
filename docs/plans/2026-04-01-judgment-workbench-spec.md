# Judgment Workbench Spec

> **Date:** 2026-04-01
> **Status:** draft v0
> **Plane:** judgment
> **Depends on:** Workspace Protocol Spec, Judgment Workbench Contract

## Goal

Define the operator-facing product surface for acceptance, evaluation, and
exploratory review in SpecOrch.

The Judgment Workbench exists so the system’s reasoning becomes visible and
reviewable instead of being collapsed into a final pass/warn/fail output.

## User Problem

Today, SpecOrch already produces real acceptance artifacts and evidence, but
the operator experience is still too artifact-first and too evaluator-shaped.

That creates three problems:

1. it is hard to see what was actually evaluated
2. it is hard to understand why the current judgment exists
3. it is hard to distinguish confirmed problems from candidate concerns

## Jobs To Be Done

When I open an acceptance or review surface, I want to:

1. understand what the system decided to evaluate
2. see the evidence bundle behind that evaluation
3. understand the current judgment and why it exists
4. review candidate findings as first-class objects
5. compare current evidence and judgment against a baseline when needed

## Primary Pages and Panels

## 1. Workspace Judgment Overview

Every workspace should expose a compact judgment panel.

Minimum contents:

- active base run mode
- evidence bundle summary
- current judgment class
- compare status
- count of confirmed issues and candidate findings
- next recommended review step

This is the shortest path for answering:

- what are we currently concluding about this work

## 2. Evidence Bundle Panel

This is where the operator sees the review inputs.

It should show:

- bundle kind
- route and step coverage
- transcript and browser evidence
- screenshot or visual QA references
- relevant artifact links
- evidence summary in plain language

The goal is to make evidence navigable before reading evaluator prose.

## 3. Judgment Timeline

This is the history of how the current judgment formed.

It should show:

- routing selection
- graph profile activation
- evidence collection
- compare activation or skip
- judgment assignment
- review-state changes
- promotion or dismissal outcomes

This timeline is critical because the operator should see the path to the
verdict, not just the verdict itself.

## 4. Candidate Findings Queue

Candidate findings must be visible as named review objects.

Each row or card should show:

- claim
- surface
- why it matters
- confidence
- impact if true
- repro status
- hold reason
- promotion test
- recommended next step

This page should make uncertainty legible rather than hiding it.

## 5. Compare Overlay View

Compare is not a separate workbench. It is an overlay that explains drift.

The compare view should show:

- selected baseline
- artifact drift
- evidence drift
- judgment drift
- whether drift changed the final review outcome

The operator should be able to say:

- this judgment changed because the baseline changed
- this judgment changed even though the evidence shape stayed stable

## 6. Surface Pack Inspector

The operator should be able to inspect the active surface pack for the current
review.

It should show:

- surface name
- active critique axes
- known routes
- graph profiles
- available baselines

This prevents exploratory evaluation from feeling like hidden evaluator magic.

## Information Architecture

Recommended navigation within a workspace:

1. `Overview`
2. `Evidence`
3. `Judgment Timeline`
4. `Candidate Findings`
5. `Compare`
6. `Surface Pack`

Recommended top summary row:

- confirmed issue count
- candidate finding count
- observation count
- compare active yes/no
- evidence coverage summary

## Required Visible Concepts

The operator must see these concepts directly in the UI:

- `verify`
- `replay`
- `explore`
- `recon`
- `confirmed_issue`
- `candidate_finding`
- `observation`
- `compare active`
- `promotion test`

If those concepts stay buried in backend or evaluator payloads, the Judgment
Workbench is not actually working.

## Required States

### Judgment Class

- `confirmed_issue`
- `candidate_finding`
- `observation`

### Review State

- `queued`
- `reviewed`
- `promoted`
- `dismissed`
- `archived`

### Compare

- `inactive`
- `active`
- `drift_detected`
- `drift_not_material`

Every state should be paired with explicit reason text.

Examples:

- `candidate finding: confidence medium, impact high`
- `compare active: baseline drift affects evidence ordering only`
- `reviewed: promotion test still pending`

## User Experience Requirements

The Judgment Workbench must feel like a serious review surface, not a model
output viewer.

That means:

- no opaque evaluator summaries without evidence links
- no mixing observations and candidate findings in one undifferentiated list
- no unexplained warn/fail badges
- no hidden compare state

The operator should be able to read the page and explain the judgment to
another person.

## Current Codebase → Judgment Workbench Convergence

Judgment truth already exists, but it is spread across acceptance services and
dashboard routes.

### Current judgment producers

- `src/spec_orch/services/round_orchestrator.py`
- `src/spec_orch/services/acceptance/browser_evidence.py`
- `src/spec_orch/services/acceptance/prompt_composer.py`
- `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `src/spec_orch/services/acceptance/linear_filing.py`

### Current dashboard consumers

- `src/spec_orch/dashboard/routes.py`
- `src/spec_orch/dashboard/transcript.py`
- `src/spec_orch/dashboard/control.py`
- `src/spec_orch/dashboard/app.py`

### Required convergence

1. expose canonical `EvidenceBundle` and `Judgment` read models from the
   judgment substrate
2. render candidate findings as named review objects instead of buried review
   metadata
3. make compare overlay visible as an operator concept, not evaluator internals
4. let surface pack state explain why exploratory review behaved the way it did

## What Must Stay SpecOrch-Native

Judgment Workbench should remain opinionated about:

- evidence bundle semantics
- candidate finding lifecycle
- compare overlay semantics
- candidate review and promotion rules
- calibration and fixture linkage

These are core differentiators, not generic workbench furniture.

## Non-Goals

This spec does not define:

- live execution queue behavior
- runtime health or agent roster semantics
- long-term memory storage internals
- policy change rollout

Those belong to the Execution and Learning workbenches.

## Done Means

Judgment Workbench v1 is done when:

1. every reviewable workspace exposes a compact judgment overview
2. evidence bundle, judgment timeline, candidate findings, and compare overlay
   are first-class surfaces
3. operators can distinguish confirmed issues from candidate findings at a
   glance
4. operators can explain why the current judgment exists without opening raw
   evaluator payloads
5. surface pack state is visible enough that exploratory review no longer feels
   opaque
