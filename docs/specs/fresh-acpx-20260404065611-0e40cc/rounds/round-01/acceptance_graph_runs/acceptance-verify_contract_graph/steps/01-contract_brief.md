## Contract Brief: Fresh ACPX Mission E2E Narrow Smoke

### Mission
- **ID**: `fresh-acpx-20260404065611-0e40cc`
- **Mode**: `fresh_acpx_mission` (local-only, no artifact reuse)
- **Intent**: Prove ACPX end-to-end by scaffolding exactly two TypeScript contract files via a minimal single-wave run.

### Contract (Declared Feature)
Two files must be scaffolded inside worker workspaces:
1. `src/contracts/mission_types.ts`
2. `src/contracts/artifact_types.ts`

Both must contain valid TypeScript contract tokens, a schema surface, pass `tsc --noEmit`, pass lint smoke, and pass import smoke. Only these files may be touched; all other constraints (no dashboard changes, no test harnesses, no replay engines) apply.

### Success Conditions (All Met ✅)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Fresh mission created | ✅ | Mission bootstrapped, phase=executing |
| 2 | Plan ≤1 wave, ≤2 packets | ✅ | Wave 0, exactly 2 packets completed |
| 3 | Fresh artifacts produced | ✅ | Both files scaffolded, all 6 checks passed each |
| 4 | Workflow replay ready | ✅ | 6 review routes, 11 assertions configured |

### Verification Chain
- **Packet 1** (`acpx-contract-mission-types-scaffold`): ✅ All 6 checks passed, mergeable, in-scope
- **Packet 2** (`acpx-contract-artifact-types-scaffold`): ✅ All 6 checks passed, mergeable, in-scope
- **Round decision**: `continue` — `wave_complete_all_packets_merged`, confidence 0.98

### Directly Affected Routes
`/?mission=fresh-acpx-20260404065611-0e40cc&mode=missions&tab=overview` (primary), plus `transcript`, `approvals`, `visual_qa`, `costs`, `judgment` tabs — all to be validated by the pending workflow replay.

### Next Transition
→ **workflow_replay**: Validate post-run dashboard surfaces per the 11 workflow assertions and the configured post-run campaign.
