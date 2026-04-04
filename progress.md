# Progress

## 2026-04-04

### Session Start

- Confirmed latest `main` at `4e7c0ab`
- Created clean worktree `self-hosting-dogfood-start`
- Verified `.worktrees` is git-ignored
- Ran focused baseline suite: `67 passed`

### Current Focus

- Wave complete; ready for commit/PR
- Scope:
  - Linear drift inventory + safe backfill
  - richer plan mirror contract
  - chat-to-issue lifecycle dogfood
  - acceptance/archive closeout

### Notes

- Main repo has unrelated untracked noise; work proceeds only in the new worktree.
- The next tranche should prefer report-first Linear sync before any mass write-back.
- Task 1 complete:
  - added `linear-sync --report`
  - added `linear-sync --json`
  - added drift preview without write-back
  - verification: `50 passed`, `ruff check`, `ruff format --check`, `mypy`
- Task 2 complete:
  - added `governance_sync` to the mirror
  - mirrors latest acceptance status, latest release bundle, and next bottleneck
  - verification: `18 passed`, `ruff check`, `ruff format --check`, `mypy`
- Task 3 complete:
  - freeze now responds idempotently for already-frozen threads
  - launch metadata now keeps `conversation_thread` provenance
  - verification: `18 passed`, `ruff check`, `ruff format --check`, `mypy`
- Task 4 complete:
  - canonical acceptance full smoke passed
  - archive bundle written under `docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04`
  - `docs/acceptance-history/index.json` updated
  - repo-level verification: `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy src/spec_orch/`
- Post-closeout hardening:
  - found a remaining artifact hygiene gap after the green acceptance run
  - root cause was not the acceptance status writer, but absolute paths leaking through fresh `docs/specs/*` source-run carriers
  - fixed by adding mission-tree text artifact sanitization and wiring it into both fresh ACPX harnesses
  - refreshed the current mission/exploratory source runs in place and rebuilt the release bundle against the latest fresh mission ids
  - fresh verification after the fix:
    - `111 passed`
    - `ruff check src/ tests/`
    - `ruff format --check src/ tests/`
    - `mypy src/spec_orch/`
    - `rg -n '/Users/chris/|/private/var/' docs/specs/fresh-acpx-* .spec_orch/acceptance docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04` returned no matches
