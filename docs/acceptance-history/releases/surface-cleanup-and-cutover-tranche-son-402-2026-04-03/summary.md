# Surface Cleanup and Cutover Tranche SON-402 2026-04-03

- Overall status: `pass`
- Reported checks: `4/4`
- Git commit: `1e662f9e24fa039c8e98bc7000d5633f27ce0d22`
- Acceptance suite version: `formal-acceptance-v1`

## Checks

- Issue Start: `pass`
- Mission Start: `pass`
- Dashboard UI: `pass`
- Exploratory: `pass`

## Notes

- This bundle captures `SON-402` tranche 1 by making `Execution`, `Judgment`, and `Learning` the canonical operator workbench surfaces while preserving raw `Acceptance` as a compatibility bridge.
- Legacy mission acceptance deep links now normalize onto `Judgment`, the mission `Acceptance` tab is removed, and `Judgment Workbench` exposes `Open raw acceptance artifact` for compatibility.
- Source-run compare versus `learning-workbench-tranche-son-396-2026-04-03`: `issue_start` stayed on `SPC-1`; `mission_start` advanced to `fresh-acpx-20260403054744-924ad5`; `exploratory` advanced to `fresh-acpx-20260403055337-dde207`.
- A tranche-closeout `harness_bug` in fresh mission workflow replay was repaired by migrating campaign routes and interaction plans from `acceptance` to `judgment`; final reruns closed with `0 harness_bug / 0 n2n_bug / 0 ux_gap`.
