# Memory Context Layering Contract Tranche 1 2026-04-04

- Overall status: `pass`
- Reported checks: `4/4`
- Git commit: `ece4a57cb5b5274edb6d1bc70120a8a3218cb903`
- Acceptance suite version: `formal-acceptance-v1`

## Checks

- Issue Start: `pass`
- Mission Start: `pass`
- Dashboard UI: `pass`
- Exploratory: `pass`

## Notes

- This bundle captures Task 1 of phase-2 hardening by separating execution, evidence, archive lineage, and promoted learning into explicit context layers.
- Context assembly and memory service helpers now preserve layer boundaries instead of returning one undifferentiated memory bucket, and read models declare which layers they are allowed to consume.
- Source-run compare versus showcase-narrative-layer-tranche-son-363-source-run-compare-2026-04-03: issue_start stayed on SPC-1; dashboard_ui stayed on dashboard-ui-local; mission_start advanced to fresh-acpx-20260404035207-87c533; exploratory advanced to fresh-acpx-20260404040228-c8f454.
- Closeout fixed three real issue-start harness/runtime bugs: the smoke fixture no longer expects a trailing newline, stale nested issue worktrees are reset before reruns, and ACPX progress detection now treats descriptive execute-tool titles as real progress so reconnect retries do not overwrite successful work with degraded retry artifacts.
