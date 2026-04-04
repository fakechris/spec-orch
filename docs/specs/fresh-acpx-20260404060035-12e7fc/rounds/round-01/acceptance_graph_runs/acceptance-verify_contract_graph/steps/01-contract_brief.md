## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Contract
| Attribute | Value |
|-----------|-------|
| Mission ID | fresh-acpx-20260404060035-12e7fc |
| Title | Fresh ACPX Mission E2E Narrow Smoke |
| Execution Mode | fresh_acpx_mission |
| Scope | Local-only, narrow proof |

### Acceptance Criteria
1. ✅ A fresh mission can be created for this run
2. ✅ The plan stays within one wave and at most two work packets
3. ✅ The mission can be launched and produce fresh round artifacts
4. ⏳ Post-run workflow replay can validate the resulting dashboard surfaces *(pending)*

### Constraints Compliance
| Constraint | Status |
|------------|--------|
| Keep first fresh mission path narrow and local-only | ✅ Satisfied |
| Do not reuse historical round artifacts as fresh proof | ✅ Satisfied |
| Plan budget: at most 1 wave and at most 2 work packets | ✅ Satisfied |
| Only touch src/contracts/mission_types.ts and src/contracts/artifact_types.ts | ✅ Satisfied |
| Do not implement dashboard runtime changes, test harnesses, or replay engines | ✅ Satisfied |

### Fresh Execution Results (Round 1)
- **Decision**: Continue with confidence 0.99
- **Work Packets**: 2/2 succeeded
  - `acpx-fresh-scaffold-mission-types` ✅
  - `acpx-fresh-scaffold-artifact-types` ✅
- **Verification**: All 6 steps passed per packet (scaffold_exists, contract_tokens, schema_surface, typecheck, lint_smoke, import_smoke)
- **Gate Verdicts**: Both mergeable with correct scope

### Success Conditions
- **This Step**: Contract summary confirms declared feature (fresh ACPX E2E) and affected routes identified
- **Next Phase**: Workflow replay must validate 11 dashboard assertions across primary and related routes
