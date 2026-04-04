## Route Replay Evidence

### Step: route_replay
**Mission**: Fresh ACPX Mission E2E Narrow Smoke (`fresh-acpx-20260404115946-e74704`)

### Contract Evidence Captured

#### Fresh Execution Results
- **Round 1**: Completed (2026-04-04T12:00:02 → 12:02:50)
- **Workers**: 2 (both succeeded)
  - `acpx-fresh-contract-mission-types` ✓
  - `acpx-fresh-contract-artifact-types` ✓

#### Artifact Verification (6 Steps Each)
1. **scaffold_exists**: ✓ Both files present in worker workspaces
2. **typescript_contract_tokens**: ✓ All files contain `export`, `interface`, `type`, or `enum`
3. **typescript_schema_surface**: ✓ All files expose Schema/schema surface
4. **typescript_typecheck**: ✓ `tsc --noEmit` passes for both files
5. **typescript_lint_smoke**: ✓ No trailing whitespace, no tabs, proper newline termination
6. **typescript_import_smoke**: ✓ Import smoke test passes via tsc

#### Gate Verdicts
- `acpx-fresh-contract-mission-types`: **MERGEABLE** - scope clean, all in-scope
- `acpx-fresh-contract-artifact-types`: **MERGEABLE** - scope clean, all in-scope

### Workflow Replay Validation

#### Primary Routes Verified
- `/` - Dashboard root ✓
- `/?mode=missions` - Mission inventory ✓
- `/?mission=fresh-acpx-20260404115946-e74704&mode=missions&tab=overview` ✓

#### Related Routes Verified
- transcript tab ✓
- approvals tab ✓
- judgment tab ✓
- visual QA tab ✓
- costs tab ✓

#### Workflow Assertions
All 11 assertions validated:
1. Launcher panel opens from header ✓
2. Needs attention mode selectable ✓
3. Missions mode selectable ✓
4. Decision queue mode selectable ✓
5. Deep evidence mode selectable ✓
6. Target mission selectable from list ✓
7. Transcript tab opens from detail ✓
8. Approvals surface exposes controls ✓
9. Visual QA tab opens ✓
10. Judgment tab opens ✓
11. Costs tab opens ✓

### Conclusion
**Route replay successfully captured all contract evidence.** The fresh ACPX mission produced two verified TypeScript contract files that passed all verification gates. The post-run dashboard workflow replay confirmed all declared routes are functional and all workflow assertions pass. Both artifacts are mergeable and ready for integration.
