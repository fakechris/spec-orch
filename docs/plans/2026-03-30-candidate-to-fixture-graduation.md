# Candidate-to-Fixture Graduation

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Implemented baseline audit trail

## Goal

Define how repeated reviewed candidate findings become calibration assets
without waiting for full memory linkage.

## Graduation Stages

Current implemented stages:

- `fixture_candidate`
- `regression_asset`

These sit above the judgment classes:

- `observation`
- `candidate_finding`
- `confirmed_issue`

## Current Rule

A judgment may qualify for `fixture_candidate` when:

- it is a `candidate_finding`
- it has been reviewed repeatedly
- repeat count reaches the local threshold

Current baseline threshold in code:

- `repeat_count >= 3`

## Audit Trail

Graduation events are file-backed and append-only.

Current path:

- `docs/specs/<mission_id>/operator/fixture_graduations.jsonl`

Each event records:

- `judgment_id`
- `stage`
- `summary`
- `source_record_id`
- `evidence_refs`

## Why This Stops At Audit Trail

Epic 4 should establish:

- rules
- event shape
- append-only evidence

It should not yet:

- auto-promote into memory
- auto-create regression fixtures
- auto-wire evolution policies

Those belong to Epic 5 and Epic 6.
