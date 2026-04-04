## Contract Assertion: FAIL

### Summary
The contract does **not hold** due to a scope constraint violation.

### Acceptance Criteria
| Criterion | Status |
|-----------|--------|
| Fresh mission can be created | ✅ PASS |
| Plan within 1 wave / 2 packets | ✅ PASS |
| Mission launched with fresh artifacts | ✅ PASS |
| Post-run workflow replay | ⏳ PENDING |

### Constraint Checks
| Constraint | Status |
|------------|--------|
| Narrow local-only path | ✅ PASS |
| No historical artifact reuse | ✅ PASS |
| Budget: 1 wave, ≤2 packets | ✅ PASS |
| Only touch allowed contract files | ❌ **FAIL** |
| No dashboard runtime changes | ✅ PASS |

### Failure Detail
- **Packet**: `acpx-fresh-0-002`
- **Issue**: Out-of-scope file written: `telemetry/events.jsonl`
- **Allowed files**: `src/contracts/artifact_types.ts`
- **Gate verdict**: `mergeable=false` (scope condition failed)

### Contract Artifacts Verification
Both contract files are structurally correct:
- `mission_types.ts` — all verification checks passed
- `artifact_types.ts` — all verification checks passed

### Decision
**CONTRACT NOT HELD** — requires retry with tighter scope enforcement or suppressed telemetry logging.
