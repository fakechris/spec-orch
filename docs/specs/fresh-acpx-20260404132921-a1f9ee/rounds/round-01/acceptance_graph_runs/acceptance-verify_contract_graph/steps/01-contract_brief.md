## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Feature Summary
Scaffold two TypeScript contract files (`mission_types.ts` and `artifact_types.ts`) under `src/contracts/` as a minimal fresh proof of ACPX mission execution.

### Acceptance Criteria
| # | Criterion | Status |
|---|-----------|--------|
| 1 | Fresh mission can be created | ✅ Verified |
| 2 | Plan within 1 wave / ≤2 packets | ✅ Verified |
| 3 | Mission launches and produces fresh artifacts | ✅ Verified |
| 4 | Post-run workflow replay validates dashboard | ⏳ Pending workflow replay step |

### Constraints Enforced
- **Local-only**: No external network or cloud dependencies
- **No reuse**: Historical round artifacts not used as proof
- **Budget**: 1 wave max, 2 packets max
- **Scope lockdown**: Only `src/contracts/mission_types.ts` and `src/contracts/artifact_types.ts` touched
- **No extensions**: No dashboard runtime, test harnesses, or replay engines

### Wave 0 Execution Summary
| Packet | Succeeded | Scope Verified | Gate Mergeable | Verifications |
|--------|-----------|----------------|----------------|---------------|
| `fresh-acpx-mission-types-scaffold` | ✅ | ✅ | ✅ | 6/6 |
| `fresh-acpx-artifact-types-scaffold` | ✅ | ✅ | ✅ | 6/6 |

**All 6 verification steps passed per packet:** scaffold_exists, typescript_contract_tokens, typescript_schema_surface, typescript_typecheck, typescript_lint_smoke, typescript_import_smoke.

### Declared Routes (for workflow replay)
- **Primary**: `/`, `/?mode=missions`, `/?mission=fresh-acpx-...&mode=missions&tab=overview`
- **Related**: transcript, approvals, judgment tabs

### Decision
**PASS** — Fresh execution contract satisfied with 0.97 confidence. All 4 acceptance criteria satisfied for fresh execution phase. Workflow replay phase remains to validate dashboard surfaces.
