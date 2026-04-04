# Task Plan

## Goal

Use the latest hardened `spec-orch` mainline as its own internal development system:

1. detect and repair Linear/runtime drift safely
2. mirror plan/tranche/bottleneck truth into Linear in a structured way
3. run the `chat -> canonical issue -> workspace -> Linear mirror` path as a first-class dogfood workflow
4. close the wave with canonical acceptance and a release bundle

## Phases

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Fresh worktree + baseline | complete | New worktree created from `main@4e7c0ab`; focused self-hosting baseline suite green |
| 2. Plan + planning files | complete | Implementation plan and persistent working-memory files are written and updated through closeout |
| 3. Linear drift inventory + safe backfill | complete | `linear-sync --report/--json` and preview drift seam landed with drift classification |
| 4. Structured plan mirror enrichment | complete | `governance_sync` now projects acceptance status, latest bundle, and mission-local bottleneck |
| 5. Chat-to-issue dogfood hardening | complete | Freeze is now idempotent and handoff persists conversation provenance into launch metadata |
| 6. Acceptance + archive closeout | complete | Canonical suite pass, bundle written, index updated, next bottleneck recorded as Lifecycle |
| 7. Artifact hygiene hardening | complete | Fresh mission source-run trees now pass post-run path sanitization before bundle/archive handoff |

## Constraints

- Start from the latest `main` only.
- Do not redesign intake/workbench/archive architecture.
- Use TDD for each touched seam.
- Keep `Linear` writes best-effort where external failure should not corrupt local state.
- Keep `Active Context`, `Working State`, `Review Evidence`, `Archive`, and `Promoted Learning` distinct.
- After each tranche, answer the `Instructions / State / Verification / Scope / Lifecycle` review questions.

## Verification Targets

- Focused unit suite for self-hosting seams
- `ruff check src/ tests/`
- `ruff format --check src/ tests/`
- `mypy src/spec_orch/`
- Canonical acceptance full smoke before closeout
- Absolute-path scan over tracked source-run artifacts before commit/PR

## Open Questions

- Which existing Linear-bound missions currently show the highest drift once report mode exists?
- How much plan detail can we mirror into issue description without making the `SpecOrch Mirror` unreadable?
- Which step in the `chat-to-issue` path currently has the weakest lifecycle evidence?
