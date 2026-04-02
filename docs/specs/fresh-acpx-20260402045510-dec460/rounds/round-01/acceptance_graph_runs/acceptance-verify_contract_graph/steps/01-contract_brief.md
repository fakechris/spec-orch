## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Intent
Prove ACPX end-to-end execution via a minimal fresh mission that scaffolds exactly **two TypeScript contract files** in **one wave** with **two work packets**:
- `src/contracts/mission_types.ts` (worker: fresh-acpx-001)
- `src/contracts/artifact_types.ts` (worker: fresh-acpx-002)

### Success Conditions
| Condition | Status |
|-----------|--------|
| Fresh mission created and launched | ✅ Launched |
| Within 1 wave, ≤2 work packets | ✅ In scope |
| Fresh round artifacts produced | ✅ Round completed |
| Files scaffolded correctly | ✅ Both packets |
| TypeScript typecheck passes | ✅ Both packets |
| Lint smoke clean | ✅ Both packets |
| Import smoke resolves | ❌ **RETRY** (harness bug) |

### Root Cause Analysis
The `typescript_import_smoke` step failed for **both packets** due to a **verification harness bug**, not contract file defects:
- Harness writes: `import ... from './src/contracts/mission_types'`
- File location: `src/contracts/import_smoke.ts`
- Result: double-nested path `./src/contracts/` → TypeScript cannot resolve

**Contract files are valid.** Retry with corrected import paths (should be `./mission_types` and `./artifact_types`).

### Next Step
Address retry conditions to confirm deliverables pass verification.
