## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Overview
- **Mission ID**: fresh-acpx-20260404040228-c8f454
- **Title**: Fresh ACPX Mission E2E Narrow Smoke
- **Execution Mode**: fresh_acpx_mission (local-only)

### Contract Scope
| Aspect | Commitment |
|--------|------------|
| Target Files | `src/contracts/mission_types.ts`, `src/contracts/artifact_types.ts` |
| Max Waves | 1 |
| Max Packets | 2 |
| Fresh Proof | Required (no historical artifacts) |

### Acceptance Criteria
1. ✅ A fresh mission can be created for this run.
2. ✅ The plan stays within one wave and at most two work packets.
3. ✅ The mission can be launched and produce fresh round artifacts.
4. ⏳ Post-run workflow replay can validate the resulting dashboard surfaces.

### Round 1 Execution Status
- **Decision**: `continue`
- **Reason Code**: `all_packets_verified_and_mergeable`
- **Confidence**: 0.97
- **Wave 0 Objective**: Met

| Packet | Status | Verdict | Verification |
|--------|--------|---------|--------------|
| scaffold-mission-types | ✅ Succeeded | mergeable | 6/6 steps passed |
| scaffold-artifact-types | ✅ Succeeded | mergeable | 6/6 steps passed |

### Verification Results (Both Packets)
- `scaffold_exists`: ✅
- `typescript_contract_tokens`: ✅
- `typescript_schema_surface`: ✅
- `typescript_typecheck`: ✅
- `typescript_lint_smoke`: ✅
- `typescript_import_smoke`: ✅

### Scope Compliance
- All-in-scope: ✅
- Out-of-scope files touched: None
- Gate verdicts: mergeable for all packets

### Pending: Workflow Replay
- **Routes to validate**: 6 (overview, transcript, approvals, visual, costs, judgment)
- **Assertions**: 11 workflow assertions
- **Required interactions**: 4 (launcher, missions mode, mission detail, tabs)

### Conclusion
Round 1 contract obligations are fully satisfied. Both scaffold packets produced clean, verified TypeScript contracts within scope. The mission is ready to proceed to post-run workflow replay validation.
