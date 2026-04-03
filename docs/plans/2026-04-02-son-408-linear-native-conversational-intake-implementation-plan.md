# SON-408 Linear Native Conversational Intake Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a small but real Linear-native intake contract so Linear issues can be parsed, evaluated, and written back using the new conversational intake shape instead of only the legacy builder-prompt template.

**Architecture:** Add a dedicated `linear_intake` service layer that owns the new Linear issue section vocabulary and readiness semantics for SON-408, while keeping the final shared canonical schema deferred to SON-410. Adapt `LinearIssueSource`, `ReadinessChecker`, and `LinearWriteBackService` to consume this service so the feature is exercised by existing runtime paths.

**Tech Stack:** Python dataclasses, `pytest`, existing `LinearClient`, existing daemon/readiness flow

### Task 1: Add Linear intake contract tests

**Files:**
- Create: `tests/unit/test_linear_intake.py`
- Modify: `tests/unit/test_readiness_triage.py`
- Modify: `tests/unit/test_linear_issue_source.py`
- Modify: `tests/unit/test_linear_write_back.py`
- Modify: `tests/unit/test_linear_client.py`

**Step 1: Write failing tests**

Add tests for:
- parsing and rendering the new Linear intake issue sections
- computing intake authoring state from structured sections
- readiness behavior for the new intake format
- `LinearIssueSource` fallback from new intake sections into the existing `Issue` model
- `LinearWriteBackService` intake summary / canonical rewrite helpers
- `LinearClient` description update mutation

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/test_linear_intake.py tests/unit/test_readiness_triage.py tests/unit/test_linear_issue_source.py tests/unit/test_linear_write_back.py tests/unit/test_linear_client.py -q
```

Expected: failure because the `linear_intake` service and new writeback/client methods do not exist yet.

### Task 2: Implement the SON-408 Linear intake service

**Files:**
- Create: `src/spec_orch/services/linear_intake.py`

**Step 1: Write minimal implementation**

Add:
- `LinearIntakeState`
- `LinearAcceptanceDraft`
- `LinearIntakeDocument`
- parser / renderer helpers for the target Linear issue structure
- readiness-oriented helpers for acceptance completeness and blocking questions

**Step 2: Run targeted tests**

Run:

```bash
pytest tests/unit/test_linear_intake.py -q
```

Expected: pass

### Task 3: Wire existing runtime seams to the new contract

**Files:**
- Modify: `src/spec_orch/services/linear_issue_source.py`
- Modify: `src/spec_orch/services/readiness_checker.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `src/spec_orch/services/linear_client.py`

**Step 1: Adapt downstream consumers**

Implement:
- new-format parsing in `LinearIssueSource` with legacy fallback
- new-format readiness rules in `ReadinessChecker` with legacy fallback
- intake summary / canonical description rewrite helpers in `LinearWriteBackService`
- GraphQL description update mutation in `LinearClient`

**Step 2: Run targeted tests**

Run:

```bash
pytest tests/unit/test_readiness_triage.py tests/unit/test_linear_issue_source.py tests/unit/test_linear_write_back.py tests/unit/test_linear_client.py -q
```

Expected: pass

### Task 4: Verify tranche gate

**Files:**
- Modify if needed: `docs/acceptance-history/index.json`
- Modify if needed: `docs/acceptance-history/releases/<release_id>/*`

**Step 1: Run the tranche verification set**

Run:

```bash
pytest tests/unit/test_linear_intake.py tests/unit/test_readiness_triage.py tests/unit/test_linear_issue_source.py tests/unit/test_linear_write_back.py tests/unit/test_linear_client.py -q
```

Then run the canonical acceptance suite and archive flow required by the acceptance gate.

**Step 2: Commit after green**

```bash
git add docs/plans/2026-04-02-son-408-linear-native-conversational-intake-implementation-plan.md src/spec_orch/services/linear_intake.py src/spec_orch/services/linear_issue_source.py src/spec_orch/services/readiness_checker.py src/spec_orch/services/linear_write_back.py src/spec_orch/services/linear_client.py tests/unit/test_linear_intake.py tests/unit/test_readiness_triage.py tests/unit/test_linear_issue_source.py tests/unit/test_linear_write_back.py tests/unit/test_linear_client.py
git commit -m "feat: add linear conversational intake contract"
```
