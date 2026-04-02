## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Contract Summary

**Mission**: `fresh-acpx-20260402054507-93e48f` — Fresh ACPX Mission E2E Narrow Smoke

**Intent**: Prove ACPX end-to-end execution by scaffolding two minimal TypeScript contract files (`src/contracts/mission_types.ts` and `src/contracts/artifact_types.ts`) in separate worker workspaces, staying within a strict budget of 1 wave and 2 work packets, with no reuse of historical artifacts.

### Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | A fresh mission can be created for this run | ✅ Pass | Mission created, round 2 completed |
| 2 | Plan stays within 1 wave and at most 2 work packets | ✅ Pass | Exactly 1 wave, 2 packets (scaffold-mission-types, scaffold-artifact-types) |
| 3 | Mission can be launched and produce fresh round artifacts | ✅ Pass | Both workers succeeded; valid TypeScript files produced and typecheck/lint pass |
| 4 | Post-run workflow replay can validate dashboard surfaces | ⚠️ Pending | Campaign defined but not yet executed; human approval needed |

### Verification Results (Round 2)

Both workers passed 5 of 6 verification steps. The single failure is **typescript_import_smoke**, which is caused by a bug in the verification script itself, not in the produced files:

- The harness writes `src/contracts/import_smoke.ts`
- It then imports `'./src/contracts/mission_types'` from within that file
- Since `import_smoke.ts` is already inside `src/contracts/`, the correct relative path would be `'./mission_types'`

**Result**: False negative on otherwise correct TypeScript files. Both `mission_types.ts` and `artifact_types.ts` pass:
- ✅ scaffold_exists
- ✅ typescript_contract_tokens
- ✅ typescript_schema_surface
- ✅ typescript_typecheck (tsc --noEmit)
- ✅ typescript_lint_smoke (no trailing whitespace, no tabs, terminal newline)
- ❌ typescript_import_smoke (verification harness bug)

### Blocking Decision

The orchestrator issued `ask_human` with `verification_script_bug_requires_fix`. Three options were presented:

1. **Fix the verification script and retry** — correct the import path and re-run verification
2. **Accept 5/6 as sufficient** — treat import_smoke failure as a known-verification-bug and proceed to workflow replay
3. **Alternative approach**

**Confidence**: 0.85 that the files are correct; 1.0 that the verification harness has the bug.

### Post-Run Workflow Campaign

Once the blocking question is resolved, a workflow replay campaign is scheduled to validate:
- Launcher panel from header
- Mission inventory / mission list
- Fresh mission detail (overview, transcript, approvals, visual QA, costs, acceptance tabs)

### Constraints Compliance

| Constraint | Compliance |
|------------|------------|
| Narrow/local-only path | ✅ |
| No historical artifact reuse | ✅ |
| ≤1 wave, ≤2 packets | ✅ |
| Only touch allowed files | ✅ |
| No dashboard/test harness/replay implementation | ✅ |

### Recommendation

The contract files themselves are substantively correct (5/6 verifications including typecheck and lint). The `typescript_import_smoke` failure is a self-referential harness bug that was also present in Round 1 and not fixed. Proceeding with option (b) — accepting the files and treating the smoke test as a known-verification-bug — is reasonable, but option (a) would close the loop on the harness defect for future runs.
