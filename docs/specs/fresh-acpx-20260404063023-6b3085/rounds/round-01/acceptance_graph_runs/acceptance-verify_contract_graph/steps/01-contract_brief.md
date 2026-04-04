## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Purpose
Verify the declared feature (fresh ACPX mission execution) and validate directly affected routes (dashboard surfaces).

### Acceptance Criteria
1. ✅ **Fresh mission creation** — A fresh mission can be created for this run.
2. ✅ **Plan budget compliance** — Plan stays within 1 wave and at most 2 work packets.
3. ✅ **Fresh round artifacts** — Mission launches and produces fresh round artifacts.
4. ⏳ **Post-run dashboard validation** — Workflow replay validates resulting dashboard surfaces.

### Constraints (All Satisfied)
- ✅ Narrow, local-only execution path
- ✅ No reuse of historical round artifacts
- ✅ At most 1 wave, at most 2 work packets
- ✅ Only touched `src/contracts/mission_types.ts` and `src/contracts/artifact_types.ts`
- ✅ No dashboard runtime, test harnesses, or replay engine implementation

### Round 1 Results
| Packet | Status | Files | Verification |
|--------|--------|-------|--------------|
| scaffold-mission-types | ✅ Passed | src/contracts/mission_types.ts | All 6 checks passed |
| scaffold-artifact-types | ✅ Passed | src/contracts/artifact_types.ts | All 6 checks passed |

### Verified Properties
- TypeScript compilation: passed (tsc --noEmit)
- Import smoke: passed
- Lint smoke: passed (no trailing whitespace, no tabs)
- Schema surface: confirmed (Schema, export interface, export type)
- Scope compliance: 100% (all realized files match allowed files)
- Gate mergeable: true (no failed conditions)

### Next Phase
**Workflow Replay** — Validate post-run dashboard surfaces with 11 workflow assertions across 6 review routes (overview, transcript, approvals, visual QA, costs, judgment).
