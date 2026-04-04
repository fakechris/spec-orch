# Findings

## Research-Derived Requirements

- Use a fixed 5-subsystem tranche review language:
  - `Instructions`
  - `State`
  - `Verification`
  - `Scope`
  - `Lifecycle`
- After each tranche, identify the lowest-scoring subsystem and treat it as the next bottleneck.
- Use an explicit context/memory taxonomy:
  - `Active Context`
  - `Working State`
  - `Review Evidence`
  - `Archive`
  - `Promoted Learning`
- Exploratory acceptance should add three planning rounds before execution:
  - `functional_plan`
  - `adversarial_plan`
  - `coverage_gaps`
  - then emit a `merged_plan`
- Browser/feature acceptance should emit step-level markers:
  - `STEP_PASS`
  - `STEP_FAIL`
  - `STEP_SKIP`
- Failure evidence should include:
  - `step_id`
  - `expected`
  - `actual`
  - `screenshot_path`
  - `before_snapshot_ref`
  - `after_snapshot_ref`
- Internal production workflow/skill docs should standardize:
  - `Overview`
  - `When to Use`
  - `Workflow`
  - `Rules`
  - `Common Rationalizations`
  - `Red Flags`
  - `Verification`

## Current Codebase Gaps

- No explicit exploratory planning-round carriers exist in acceptance code.
- No `STEP_PASS/FAIL/SKIP` marker contract exists in browser evidence.
- Current judgment/workbench `coverage_gaps` usage is unrelated to exploratory planning protocol.
- Existing phase-2 hardening closed governance/context/judgment seams, so this wave should extend protocols rather than redesign carriers.
