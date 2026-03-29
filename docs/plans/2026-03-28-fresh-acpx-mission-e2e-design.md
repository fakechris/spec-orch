# Fresh Acpx Mission E2E Design

## Goal

Define the first narrow, repeatable `Fresh Acpx Mission E2E` path.

This path must prove more than dashboard workflow operability. It must prove that a brand-new mission can be created, launched, picked up, executed by a fresh ACPX builder flow, and then validated through post-run dashboard acceptance.

## Proof Boundary

This design exists to prevent over-claiming.

What counts as fresh proof:

- a mission id created for this run
- bootstrap metadata tied to that mission id
- launch metadata tied to that mission id
- daemon pickup or equivalent runner evidence tied to that mission id
- a fresh round directory produced by that run
- at least one builder execution summary tied to that fresh round
- post-run workflow replay against the mission surfaces produced by that fresh run

What does not count as fresh proof:

- replaying against an older smoke mission
- browsing a dashboard route that already existed before this run
- reusing historical round artifacts without a new bootstrap and launch trail
- treating workflow replay success as evidence that ACPX executed fresh work

## First Narrow Path

The first implementation should stay intentionally small:

- one fresh local mission
- one supported approve / plan / launch path
- one daemon or equivalent pickup path
- one fresh round with minimal packet count
- one post-run workflow replay campaign

The purpose of the first path is repeatability and proof clarity, not broad provider abstraction.

After the first path proves out, hardening should extend it in controlled ways:

- keep the default `default` variant as the narrow reference proof
- add a `multi_packet` variant so proof is not tied to exactly one packet combination
- add a `linear_bound` variant so at least one launcher path binds Linear issue context before launch
- keep all variants on the same proof split:
  - fresh execution proof
  - post-run workflow replay proof
  - remaining gaps

## Proof Checkpoints

The run should be considered successful only when all checkpoints have evidence:

1. Mission bootstrap
   - a fresh mission request exists
   - the mission id is unique for this run
   - bootstrap metadata is written to `mission_bootstrap.json`
2. Launch
   - the mission is approved and planned
   - launch produces real lifecycle metadata in `launch.json`
3. Daemon pickup
   - a live runner picks up the mission
   - pickup evidence is written to `daemon_run.json`
4. Builder execution
   - at least one fresh packet runs through ACPX
   - execution evidence is written to `builder_execution_summary.json`
5. Post-run workflow replay
   - dashboard replay runs against the fresh mission
   - browser evidence is written to `browser_evidence.json`
   - acceptance output is written to `acceptance_review.json`
6. Final reporting
   - a final report says what was proven by fresh execution
   - a final report says what was only proven by replay
   - a final report says what remains unproven

## Artifact Contract

The first `Fresh Acpx Mission E2E` run must emit:

- `mission_bootstrap.json`
- `launch.json`
- `daemon_run.json`
- `fresh_round_summary.json`
- `builder_execution_summary.json`
- `browser_evidence.json`
- `acceptance_review.json`
- `fresh_acpx_mission_e2e_report.md`

## Failure Classes

Every failed run should classify itself into one of these buckets:

1. Mission bootstrap failure
   - the mission could not be created or the bootstrap payload was invalid
2. Launch failure
   - approve / plan / launch failed or produced incomplete lifecycle data
3. Daemon pickup failure
   - the mission never transitioned into a picked-up execution state
4. Builder execution failure
   - a fresh round exists but ACPX execution did not complete usable work
5. Post-run replay failure
   - the fresh mission ran, but dashboard workflow replay failed afterward
6. Variant contract failure
   - the selected fresh variant required launcher or budget behavior that the run did not satisfy

## Reporting Rule

The final run report must always separate:

- fresh execution proof
- post-run workflow replay proof
- remaining gaps

If one part fails, the report must not silently collapse the distinction.
