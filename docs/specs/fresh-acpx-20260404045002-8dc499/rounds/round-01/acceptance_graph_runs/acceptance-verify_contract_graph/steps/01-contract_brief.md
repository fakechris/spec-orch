## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Overview
**Mission ID:** `fresh-acpx-20260404045002-8dc499`  
**Title:** Fresh ACPX Mission E2E Narrow Smoke  
**Execution Mode:** fresh_acpx_mission (local-only)

### Contract Intent
Create a minimal fresh local-only mission that proves ACPX execution by scaffolding exactly two TypeScript contract files under `src/contracts/`:
- `mission_types.ts` - Type definitions for mission contracts
- `artifact_types.ts` - Type definitions for artifact contracts

### Plan Budget
| Metric | Allowed | Realized |
|--------|---------|----------|
| Waves | ≤1 | 1 |
| Work Packets | ≤2 | 2 |

### Scope Definition
**In Scope (Allowed Files):**
- `src/contracts/mission_types.ts`
- `src/contracts/artifact_types.ts`

**Out of Scope:**
- Dashboard runtime changes
- Test harnesses
- Replay engines

### Success Conditions (Acceptance Criteria)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Fresh mission can be created | ✅ Pass | Mission created |
| 2 | Plan stays within 1 wave, ≤2 packets | ✅ Pass | 1 wave, 2 packets |
| 3 | Mission launches and produces fresh artifacts | ✅ Pass | Round 1 complete, artifacts generated |
| 4 | Post-run workflow replay validates dashboard | ⏳ Pending | Workflow replay step configured |

### Round 1 Execution Summary
- **Duration:** ~195 seconds
- **Workers:** 2 (both succeeded)
- **Verification Gates:** All 6 gates passed per worker
- **Scope Compliance:** Clean (no out-of-scope files)
- **Decision:** `continue` with confidence 0.98

### Next Phase
The fresh execution proof is complete. The contract verification should proceed to **workflow replay** to validate the post-run dashboard surfaces using the 6 configured review routes and 11 workflow assertions.
