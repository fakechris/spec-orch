## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Contract
This is a **fresh execution** proof mission with a **workflow replay** component. The goal is to prove that the ACPX system can:
1. Scaffold two minimal TypeScript contract files (`mission_types.ts`, `artifact_types.ts`) under `src/contracts/`
2. Validate the contracts pass type checking and smoke verification
3. Produce dashboard surfaces that pass post-run workflow replay

### Success Conditions

| Criterion | Status |
|-----------|--------|
| Fresh mission created | ✅ Pass |
| Plan within 1 wave / 2 packets | ✅ Pass |
| Mission launched, artifacts produced | ⚠️ Partial (1/2 files) |
| Workflow replay validates dashboard | ⏸️ Blocked (awaiting artifacts) |

### Round 1 Results
- **scaffold-mission-types**: Builder succeeded, file created, but `import_smoke` verification failed due to wrong relative path in the test script (imports `'./src/contracts/mission_types'` from within `src/contracts/` instead of `'./mission_types'`)
- **scaffold-artifact-types**: Builder failed to produce any output file despite scaffold check passing

### Required Fixes for Retry
1. **scaffold-mission-types**: The verification harness writes `import_smoke.ts` inside `src/contracts/` and incorrectly imports `'./src/contracts/mission_types'`; fix to `'./mission_types'`
2. **scaffold-artifact-types**: Builder must actually create `src/contracts/artifact_types.ts` with valid TypeScript contract content

### Workflow Replay Routes (pending successful round)
- Overview, Transcript, Approvals, Visual QA, Costs, Acceptance tabs under mission detail
- 11 workflow assertions to validate dashboard surfaces
