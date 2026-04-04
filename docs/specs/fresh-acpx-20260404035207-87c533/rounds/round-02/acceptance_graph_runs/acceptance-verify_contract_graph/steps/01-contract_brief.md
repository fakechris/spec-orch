## Contract Brief - Fresh ACPX Mission E2E Narrow Smoke

### Mission Summary
A narrow end-to-end smoke test for the ACPX mission system that:
1. Creates a fresh local-only mission
2. Executes one wave with exactly two work packets
3. Produces TypeScript contract artifacts via acpx_worker adapters
4. Validates the post-run dashboard workflow surfaces

### Success Conditions (Acceptance Criteria)
| # | Criterion | Status |
|---|-----------|--------|
| 1 | A fresh mission can be created for this run | ✅ |
| 2 | Plan stays within one wave and at most two work packets | ✅ |
| 3 | Mission can be launched and produce fresh round artifacts | ✅ |
| 4 | Post-run workflow replay can validate dashboard surfaces | ⏳ (next phase) |

### Verification Gate Results (Round 2)
| Packet | Scaffold | Tokens | Schema | Typecheck | Lint | Import | Mergeable | Scope |
|--------|----------|--------|--------|-----------|------|--------|-----------|-------|
| acpx-fresh-0-001 (mission_types.ts) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| acpx-fresh-0-002 (artifact_types.ts) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Wave Status
- **Wave 0**: COMPLETE
- **Decision**: `continue` (reason: wave_complete)
- **Confidence**: 0.95
- **Failed Conditions**: None

### Constraints Compliance
- ✅ Local-only path maintained
- ✅ No historical artifact reuse
- ✅ Budget: 1 wave / 2 packets (exactly)
- ✅ Only touched allowed contract files in worker workspaces
- ✅ No dashboard runtime, test harness, or replay engine implementation

### Proof Split
1. **Fresh Execution**: Mission launched, two workers produced TypeScript contract artifacts, all verification steps passed
2. **Workflow Replay**: Post-run dashboard validation campaign queued with 11 workflow assertions across 6 review routes

### Next Step
Advancing to mission completion workflow - post-run dashboard replay validation.
