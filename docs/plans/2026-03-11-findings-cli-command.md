# findings CLI command

## Background / Overview

The Finding store (`finding_store.py`) and Finding model were added in
Phase 3 of the architecture evolution, but there is no CLI surface for
interacting with findings.  Users need a way to list, inspect, and
resolve findings from the terminal during the review convergence loop.

This feature adds a `spec-orch findings` command group with three
subcommands: `list`, `resolve`, and `add`.

## File Changes

- Modify `src/spec_orch/cli.py` to add a `findings` command with subcommands:
  - `findings list <issue_id>` — show all findings for an issue, with
    color-coded severity and resolved status
  - `findings resolve <issue_id> <finding_id>` — mark a finding as resolved
  - `findings add <issue_id>` — add a finding from CLI flags
    (`--source`, `--severity`, `--description`, `--file-path`, `--line`,
    `--scope`, `--confidence`)
- Add tests in `tests/unit/test_cli_smoke.py` for the three findings subcommands

## Acceptance Criteria

- `spec-orch findings list SPC-X` prints findings in a readable table
- `spec-orch findings resolve SPC-X f1` marks finding f1 as resolved
- `spec-orch findings add SPC-X --source gemini --severity blocking --description "path traversal"` creates a new finding
- All new tests pass
- ruff check and mypy pass with zero errors
- Existing 138 tests still pass

## Constraints

- Use the existing `finding_store.py` service — do not duplicate persistence logic
- Follow existing CLI patterns (typer, repo-root option, echo output)
- Findings subcommands should work on the issue workspace path

## Architecture Notes

The finding_store module already provides `load_findings()`,
`append_finding()`, `resolve_finding()`, and `fingerprint_from()`.
The CLI commands simply wire these to typer with appropriate formatting.
