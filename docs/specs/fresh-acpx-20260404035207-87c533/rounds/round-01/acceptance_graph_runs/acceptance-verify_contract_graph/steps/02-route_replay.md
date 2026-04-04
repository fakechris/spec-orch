## Route Replay Step Review

### Summary
Captured contract evidence for declared dashboard routes associated with mission `fresh-acpx-20260404035207-87c533`. All 11 workflow assertions are declared for the post-run replay campaign.

### Contract Evidence Status
| Worker | Artifact | Verification | Gate | Scope |
|--------|----------|--------------|------|-------|
| acpx-fresh-0-001 | mission_types.ts | ✅ All Pass | ✅ Mergeable | ✅ Clean |
| acpx-fresh-0-002 | artifact_types.ts | ✅ All Pass | ❌ Blocked | ❌ Contaminated |

### Route Declaration Captured
- **Primary Routes**: `/`, `/?mode=missions`, `/?mission=...&tab=overview`
- **Related Routes**: transcript, approvals, judgment tabs
- **Extended Routes**: visual_qa, costs tabs

### Blocking Issue
Round 1 decision was **retry** due to `scope_contamination_retryable`. Worker acpx-fresh-0-002 realized `telemetry/events.jsonl` which is out-of-scope. All TypeScript contract verifications passed, but the scope guard blocked mergeability.

### Required Action
Retry with:
1. Tighter scope enforcement for acpx-fresh-0-002
2. Suppressed agent telemetry logging to prevent out-of-scope file creation
3. Only `src/contracts/artifact_types.ts` in realized scope

### Evidence Availability
Once scope contamination is resolved, route_replay can proceed to validate:
- Dashboard route accessibility
- Tab navigation (transcript, judgment, approvals, visual_qa, costs)
- Workflow assertion coverage
- Post-run mission detail surfaces
