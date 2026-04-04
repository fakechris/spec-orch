## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Intent
Prove fresh ACPX execution by scaffolding two minimal TypeScript contract files in a local-only mission, staying within a 1-wave/2-packet budget, then validating the resulting dashboard surfaces via post-run workflow replay.

### Acceptance Criteria
| # | Criterion | Status |
|---|-----------|--------|
| 1 | Fresh mission created | ✅ |
| 2 | Plan within 1 wave / ≤2 packets | ✅ |
| 3 | Fresh round artifacts produced | ✅ (both workers succeeded) |
| 4 | Post-run workflow replay validates dashboard | ⏳ (pending) |

### Constraints
- **Local-only**: No external network or historical artifact reuse
- **Scope lockdown**: Only `src/contracts/mission_types.ts` and `src/contracts/artifact_types.ts`
- **No dashboard/replay implementation**: Only proof artifacts during fresh run

### Round 1 Verdict
| Worker | Contract Verified | Gate Mergeable | Scope | Action |
|--------|------------------|----------------|-------|--------|
| acpx-fresh-0-001 | ✅ All checks passed | ✅ True | ✅ Clean | Ready |
| acpx-fresh-0-002 | ✅ All checks passed | ❌ False | ❌ telemetry/events.jsonl out-of-scope | **Retry** |

### Root Cause
acpx-fresh-0-002 produced correct contract artifact (`artifact_types.ts`) but the agent's telemetry logging created `telemetry/events.jsonl`, which is outside the allowed file scope.

### Recommended Next Step
**Retry** with either:
1. Tighter scope enforcement at the agent/adapter layer
2. Suppressed telemetry logging in worker execution
3. Explicit `.gitignore` or workspace filtering to exclude telemetry directories from scope validation
