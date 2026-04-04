## Route Replay Contract Verification

### Status: Awaiting Evidence Capture

The `route_replay` step has been identified for mission `fresh-acpx-20260404132336-929e89`. The contract declares **6 review routes** and **11 workflow assertions** that must be validated through replay.

### Contract Basis

From `workflow_replay` in proof_split:
- **Review Routes**: overview, transcript, approvals, visual_qa, costs, judgment tabs
- **Workflow Assertions**: Navigation flows, tab access, operator controls

### Prerequisite Check: PASSED

- Fresh execution completed successfully (Round 1, Wave 0)
- Both packets (mission_types, artifact_types) passed all verification checks
- Gate verdicts: both mergeable with `all_in_scope=true`
- TypeScript compilation clean

### Pending Actions

1. Execute route replay to capture dashboard surface evidence
2. Validate each declared route is navigable
3. Verify workflow assertions against actual UI behavior
4. Capture screenshots/evidence for contract verification

### Next Transition

Proceed to `route_replay_execution` to capture the declared route evidence and complete the contract graph verification.
