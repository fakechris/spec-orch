# Fresh ACPX Mission E2E Narrow Smoke

## Intent

Create one fresh local-only mission that proves ACPX execution by scaffolding exactly two tiny TypeScript contract files under src/contracts: mission_types.ts and artifact_types.ts. The first fresh path must stay minimal and only produce enough round artifacts to prove fresh execution before post-run workflow replay.

## Acceptance Criteria

- A fresh mission can be created for this run.
- The plan stays within one wave and at most two work packets.
- The mission can be launched and produce fresh round artifacts.
- Post-run workflow replay can validate the resulting dashboard surfaces.

## Constraints

- Keep the first fresh mission path narrow and local-only.
- Do not reuse historical round artifacts as fresh proof.
- Plan budget: at most 1 wave and at most 2 work packets.
- Only touch src/contracts/mission_types.ts and src/contracts/artifact_types.ts inside worker workspaces.
- Do not implement dashboard runtime changes, test harnesses, or replay engines during the fresh proof run.

## Interface Contracts

<!-- frozen APIs / schemas -->

## Active Wave

- Wave 0: Contract Freeze / Scaffold - Scaffold the two TypeScript contract files to prove fresh ACPX execution

## Active Packets

- scaffold-mission-types: Scaffold mission_types.ts contract
- scaffold-artifact-types: Scaffold artifact_types.ts contract
