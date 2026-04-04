## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission Intent
Validate ACPX execution through a minimal fresh mission that scaffolds two TypeScript contract files under src/contracts without reusing historical artifacts.

### Acceptance Criteria
1. A fresh mission can be created for this run.
2. The plan stays within one wave and at most two work packets.
3. The mission can be launched and produce fresh round artifacts.
4. Post-run workflow replay can validate the resulting dashboard surfaces.

### Success Indicators (Round 1)
- **Worker**: acpx-contract-scaffold → SUCCEEDED
- **Verification**: All 6 steps passed
  - scaffold_exists ✓
  - typescript_contract_tokens ✓
  - typescript_schema_surface ✓
  - typescript_typecheck ✓
  - typescript_lint_smoke ✓
  - typescript_import_smoke ✓
- **Gate Verdict**: mergeable=true, scope fully realized
- **Artifacts Produced**: mission_types.ts, artifact_types.ts

### Constraints
| Constraint | Status |
|------------|--------|
| 1 wave max | ✓ |
| 2 packets max | ✓ |
| Local-only | ✓ |
| No historical reuse | ✓ |
| Only allowed files touched | ✓ |

### Affected Routes (Post-Run Dashboard)
- Primary: /, /?mode=missions, overview tab
- Related: transcript, approvals, judgment tabs

### Status
Round 1 completed cleanly. All verifications passed. Ready for workflow replay validation phase.
