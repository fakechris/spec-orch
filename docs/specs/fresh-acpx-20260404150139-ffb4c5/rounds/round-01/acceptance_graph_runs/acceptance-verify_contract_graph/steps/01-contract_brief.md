## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Declared Feature
ACPX fresh mission execution pipeline, scoped to scaffolding two TypeScript contract files (`mission_types.ts` and `artifact_types.ts`) under `src/contracts`.

### Contract Summary
| Aspect | Value |
|--------|-------|
| Mission ID | `fresh-acpx-20260404150139-ffb4c5` |
| Proof Type | `fresh_execution` |
| Waves | 1 (Wave 0) |
| Packets | 2 (`scaffold-mission-types`, `scaffold-artifact-types`) |
| Scope Files | `src/contracts/mission_types.ts`, `src/contracts/artifact_types.ts` |

### Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Fresh mission can be created | ✅ Verified (Round 1 launched) |
| Plan within 1 wave, ≤2 packets | ✅ Verified (Wave 0, 2 packets) |
| Mission launches and produces fresh artifacts | ✅ Verified (both packets succeeded) |
| Post-run workflow replay validates dashboard | ⏳ Pending (workflow_replay step next) |

### Verification Gates (All Passed)

**scaffold-mission-types:**
- ✅ scaffold_exists — `src/contracts/mission_types.ts` present
- ✅ typescript_contract_tokens — exports interface/type/enum
- ✅ typescript_schema_surface — Schema/schema surface present
- ✅ typescript_typecheck — tsc --noEmit passed
- ✅ typescript_lint_smoke — no trailing whitespace/tabs
- ✅ typescript_import_smoke — import smoke test passed

**scaffold-artifact-types:**
- ✅ scaffold_exists — `src/contracts/artifact_types.ts` present
- ✅ typescript_contract_tokens — exports interface/type/enum
- ✅ typescript_schema_surface — Schema/schema surface present
- ✅ typescript_typecheck — tsc --noEmit passed
- ✅ typescript_lint_smoke — no trailing whitespace/tabs
- ✅ typescript_import_smoke — import smoke test passed

### Scope Compliance
- Both packets: `mergeable: true`, `failed_conditions: []`, `all_in_scope: true`
- Realized files exactly match allowed files
- No out-of-scope modifications

### Decision
| Field | Value |
|-------|-------|
| Action | `continue` |
| Reason | `wave_complete_no_remaining_packets` |
| Confidence | 0.95 |
| Plan Budget | Exhausted (1 wave, 2 packets) |

### Next Step
**workflow_replay** — Validate post-run dashboard surfaces per the `post_run_campaign` specification (launcher entry, mission inventory, fresh mission detail, transcript, judgment tabs).
