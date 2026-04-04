## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Intent
Prove ACPX execution via a minimal fresh local-only mission that scaffolds exactly two TypeScript contract files under `src/contracts/`.

### Success Conditions
| # | Criterion | Status |
|---|-----------|--------|
| 1 | Fresh mission can be created | ✅ Verified |
| 2 | Plan within 1 wave / 2 work packets | ✅ Verified |
| 3 | Mission launches and produces fresh round artifacts | ✅ Verified |
| 4 | Post-run workflow replay validates dashboard surfaces | ⏳ Pending (workflow_replay phase) |

### Constraints Compliance
- **Local-only**: Enforced ✅
- **No historical artifact reuse**: Enforced ✅
- **Budget (1 wave, 2 packets)**: Enforced ✅
- **File scope**: Only `src/contracts/mission_types.ts` and `src/contracts/artifact_types.ts` touched ✅
- **No runtime changes**: Enforced ✅

### Gate Verdicts
Both work packets returned **mergeable=true** with **zero failed conditions**.

### Next Step
Transition to **workflow_replay** to validate post-run dashboard surfaces (launcher entry, mission inventory, fresh mission detail, transcript tab, judgment tab).
