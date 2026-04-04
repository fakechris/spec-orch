## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Purpose
Prove fresh ACPX mission execution by scaffolding two minimal TypeScript contract files (`mission_types.ts` and `artifact_types.ts`) under `src/contracts/`. This is a narrow E2E smoke test validating the complete mission bootstrap-to-artifact pipeline.

### Contract Boundaries
- **In Scope:** Two TypeScript contract files, local-only execution, one wave, two packets max
- **Out of Scope:** Dashboard runtime changes, test harnesses, replay engines, historical artifact reuse

### Acceptance Criteria
1. ✅ Fresh mission successfully created
2. ✅ Execution bounded to ≤1 wave and ≤2 packets
3. ✅ Mission launched with fresh round artifacts produced
4. ⏳ Post-run workflow replay validates dashboard surfaces

### Wave 0 Verdict: PASSED
| Packet | Build | Verify | Merge | Scope |
|--------|-------|--------|-------|-------|
| acpx-contract-mission-types | ✅ | ✅ 6/6 | ✅ | ✅ all_in_scope |
| acpx-contract-artifact-types | ✅ | ✅ 6/6 | ✅ | ✅ all_in_scope |

### TypeScript Compliance
- `tsc --noEmit` clean for both files
- No trailing whitespace, tabs, or missing terminal newlines
- Import smoke tests pass

### Remaining Work
The **fresh execution proof is complete**. Next phase is **workflow replay** to validate dashboard surfaces via the post-run campaign covering launcher entry, mission inventory, fresh mission detail, transcript, and judgment review.

**Decision: CONTINUE** to workflow_replay step.
