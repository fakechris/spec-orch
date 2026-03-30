# Acceptance Compare Calibration Harness

**Date:** 2026-03-30  
**Epic:** Epic 4 — Acceptance Judgment and Calibration  
**Status:** Implemented baseline

## Goal

Make compare-style calibration a first-class acceptance concept instead of an
implicit evaluator habit.

## Core Rule

`compare` is an overlay, not a sibling acceptance mode.

Base run modes remain:

- `verify`
- `replay`
- `explore`
- `recon`

The compare overlay means:

- current review output is evaluated against a known calibration fixture
- mismatches are recorded explicitly by semantic field

## Current Harness

The baseline comparison seam lives in:

- `src/spec_orch/acceptance_core/calibration.py`

It provides:

- fixture loading
- field-level semantic comparison
- aggregate harness summary

## Comparison Schema

Each comparison records:

- `fixture_name`
- `matches`
- `mismatches`
- `expected_status` / `actual_status`
- `expected_acceptance_mode` / `actual_acceptance_mode`
- `expected_coverage_status` / `actual_coverage_status`

## Current Fixture Sources

The baseline harness currently uses:

- `tests/fixtures/acceptance/*.json`

This is intentionally narrow. Epic 4 does not yet generalize calibration to all
surfaces.

## Non-Goals

- no dashboard redesign
- no broad acceptance runtime rewrite
- no automatic promotion into memory/evolution
