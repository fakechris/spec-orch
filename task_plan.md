# Acceptance Hardening Protocol Start

## Goal

Absorb the latest harness review and UI-test research into the existing acceptance/hardening stack without changing the main architecture.

## Phases

| Phase | Status | Notes |
|---|---|---|
| Baseline verification | completed | New worktree is clean; focused baseline pytest passed. |
| Execution plan + planning files | in_progress | Create implementation plan and capture research-derived requirements. |
| 5-subsystem review checklist + context taxonomy | completed | Agent guides now carry the fixed review language, bottleneck-first ritual, and context taxonomy. |
| Exploratory acceptance planning contract | completed | `AcceptanceCampaign`, prompt composition, and exploratory review payloads now carry the three planning rounds plus merged plan. |
| Browser acceptance step markers + failure artifact contract | completed | Browser evidence now normalizes STEP_PASS/FAIL/SKIP and fixed failure evidence fields. |
| Internal workflow/skill doc hardening | completed | Agent guides now include workflow structure, anti-rationalization, and verification sections. |
| Acceptance/archive closeout | completed | Canonical full smoke passed, consolidated status is green, and the tranche bundle has been written to `docs/acceptance-history/`. |

## Constraints

- Start from the latest `main` in a clean worktree.
- Follow TDD: write failing tests first, watch them fail, then implement minimally.
- Keep this wave internal-facing: hardening, acceptance protocol, workflow docs.
- Preserve the current architecture; do not redesign surfaces or runtime seams.

## Open Questions

- Which existing acceptance models are best to extend for exploratory planning rounds?
- Whether browser evidence step markers should live at the interaction level only, or also be summarized in stability reports.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| None yet | - | - |
