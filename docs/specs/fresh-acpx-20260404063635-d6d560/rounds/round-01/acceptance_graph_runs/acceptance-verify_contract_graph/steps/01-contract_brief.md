## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Summary
A minimal fresh-execution proof-of-concept mission that validates ACPX workflow by scaffolding two TypeScript contract files (`mission_types.ts`, `artifact_types.ts`) under `src/contracts/` within strict budget constraints.

### Success Criteria (Round 1 — COMPLETE)
| Criterion | Status |
|-----------|--------|
| Fresh mission created | ✅ |
| Plan within 1 wave / ≤2 packets | ✅ |
| Mission launched, fresh artifacts produced | ✅ |
| Wave 0 all packets verified | ✅ |
| Both gate verdicts mergeable | ✅ |
| All scope constraints honored | ✅ |

### Scope Compliance
- **Allowed**: `src/contracts/mission_types.ts`, `src/contracts/artifact_types.ts`
- **Realized**: Exactly the two allowed files
- **Out-of-scope**: None

### Verification Steps (All Passed)
1. `scaffold_exists` — files present
2. `typescript_contract_tokens` — export/interface/type/enum tokens found
3. `typescript_schema_surface` — Schema surface tokens present
4. `typescript_typecheck` — `tsc --noEmit` clean
5. `typescript_lint_smoke` — no trailing whitespace, tabs, or missing terminal newlines
6. `typescript_import_smoke` — import smoke test passes TypeScript compilation

### Remaining Work
Post-run **workflow replay** must validate dashboard surfaces:
- Launcher panel open/close
- Mode switching (missions, decision queue, deep evidence, needs attention)
- Mission list selection → detail view
- Tab navigation (overview → transcript → judgment → approvals → visual → costs)

### Decision
**Proceed** to workflow_replay step. Fresh execution contract is satisfied with confidence 0.98.
