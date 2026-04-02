# Acceptance Phase 2 and Model Fallback Program

**Goal:** Split the next phase into two explicit programs: one for acceptance/report integrity and one for multi-model fallback, so stability work and product findings no longer mix.

**Architecture:** Acceptance phase 2 now has two owners. The first owner is the acceptance harness itself: report normalization, critique stability, and rerun discipline. The second owner is model execution resilience: provider fallback, configuration conventions, and operator-visible model routing. Harness bugs must be fixed immediately and rerun; product bugs discovered by the harness must flow into product work without contaminating report trust.

**Tech Stack:** SpecOrch acceptance harness, runtime_chain, LiteLLM adapters, `spec-orch.toml`, Linear.

## Program A: Acceptance Harness Integrity and Report Workflow

**Purpose**

Make exploratory/feature acceptance trustworthy enough that operators can use it as a real quality signal. This program owns harness bugs, report normalization, critique output stability, and the workflow for separating harness defects from product defects.

**Bug taxonomy**

- `A1: harness_bug`
  - Configuration inheritance failures
  - report normalization bugs
  - missing or misleading status aggregation
  - retry/timeout behavior that breaks reruns
- `B1: n2n_bug`
  - real end-to-end product failures found by acceptance
- `B2: ux_gap`
  - discoverability, clarity, confidence, continuity issues found by exploratory critique

**Workflow**

1. Run acceptance.
2. Triage findings into `harness_bug` vs `n2n_bug` vs `ux_gap`.
3. If `harness_bug`, fix immediately and rerun the same acceptance path before any product triage.
4. If `n2n_bug`, file into product flow with high priority and preserve the acceptance evidence.
5. If `ux_gap`, file into product flow with route, operator task, why-it-matters, and recommended fix.
6. Only treat an acceptance surface as canonical once reruns are stable and top-level report payload matches the nested review payload.

**Top-level report contract**

Every exploratory/feature acceptance surface should eventually emit the same operator-facing top-level fields:

- `status`
- `summary`
- `findings_count`
- `issue_proposal_count`
- `recommended_next_step`
- `finding_taxonomy`
- `source_run`

`source_run` should be the provenance seam that makes every finding traceable back to the exact mission/round/report artifact used to produce it.

**Execution loop**

1. Run acceptance and materialize the top-level report.
2. If the report is missing contract fields or disagrees with the nested review payload, classify it as `harness_bug`.
3. Fix `harness_bug` items immediately and rerun the same path until the top-level report is trustworthy.
4. Once the report is trustworthy, triage product findings into `n2n_bug` vs `ux_gap`.
5. Fix one product problem at a time, rerun the same acceptance path, and compare the new report against the previous `source_run`.
6. Only promote a finding into showcase/history once at least one rerun confirms either:
   - the original finding is gone, or
   - the finding persists with materially similar wording, route, and recommended fix.

**Initial scope**

- Fix exploratory top-level report normalization so top-level status/summary/findings align with nested `acceptance_review`
- Make rerun outputs stable enough to compare across at least 3 runs
- Ensure `exploratory_acceptance_smoke` and future feature acceptance surfaces write structured findings and proposals at the top level
- Define a repeatable filing workflow for `n2n_bug` and `ux_gap`

## Program B: Multi-Model Routing and Fallback

**Purpose**

Reduce provider fragility by supporting explicit model chains and fallback behavior instead of relying on single-provider happy paths. This program owns model selection, transient overload handling, provider fallback, and config conventions.

**Scope**

- Allow each major LLM role to declare a primary model and ordered fallbacks
- Distinguish transient provider errors from fatal config/auth errors
- Retry transient overloads locally before failing over
- Expose resolved provider/model/base information in artifacts and operator-readable reports
- Establish a clear `spec-orch.toml` convention for multi-model configuration that both humans and AI agents can follow

**Desired configuration shape**

- `primary`
- `fallbacks[]`
- per-entry:
  - `model`
  - `api_type`
  - `api_key_env`
  - `api_base_env`
  - optional `reason` / `priority`

**Initial scope**

- Acceptance evaluator fallback chain
- Scoper fallback chain
- Supervisor fallback chain
- Shared provider classification helpers for:
  - transient overload
  - timeout
  - auth/config failure
- README / reference docs that make model configuration obvious

## Linear Structure

Create two Epic-style issues:

1. `SON-353` `Acceptance Harness Integrity and Report Workflow`
2. `SON-354` `Multi-Model Routing and Fallback`

Each epic should contain child tasks for:

### Program A tasks

- `SON-355` normalize exploratory top-level report payload
- `SON-356` stabilize critique output across reruns
- `SON-357` define filing workflow for `harness_bug`, `n2n_bug`, and `ux_gap`
- `SON-358` add operator-facing acceptance bug taxonomy docs

### Program B tasks

- `SON-359` add shared model-chain config model
- `SON-360` wire acceptance evaluator primary+fallback chain
- `SON-361` wire scoper and supervisor fallback chain
- `SON-362` document model configuration in README/reference docs

## Current Open Bugs

**Harness bugs that should be fixed under Program A**

- exploratory smoke top-level JSON payload still reports `fail/null` when nested `acceptance_review` already contains actionable `warn + findings + issue_proposals`
- exploratory critique output still drifts between reruns and needs normalization discipline

**Product bugs currently discovered by exploratory critique**

- transcript evidence entry is hard to discover for first-time operators
- transcript surface lacks empty-state guidance when packet-level evidence is unavailable

**Model-routing gaps that should be fixed under Program B**

- no canonical primary/fallback model chain contract in `spec-orch.toml`
- fallback behavior is partially implemented ad hoc in code, not yet unified across evaluator/scoper/supervisor

## Exit Criteria

### Program A done when:

- exploratory top-level report matches nested acceptance review
- at least 3 reruns produce trustworthy top-level findings/proposals
- harness bugs are no longer mixed with product bugs in triage

### Program B done when:

- major LiteLLM roles support explicit fallback chains
- transient provider overload no longer hard-fails the whole acceptance path
- config docs clearly explain how to add a new provider/model pair
