# SON-370 Shared Operator Semantics Tranche 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a canonical shared operator semantics model for workspace, execution, judgment, and learning placeholders, then wire the intake handoff/dashboard preview onto that shared contract.

**Architecture:** Add one small domain module for operator-visible read models and one adapter module that normalizes existing intake, execution, and acceptance-core objects into those read models. Keep runtime and judgment ownership where they are today; this tranche only creates the shared language and a first consumer seam through the intake handoff payload.

**Tech Stack:** Python 3.13, dataclasses, StrEnum, existing acceptance/runtime domain models, pytest unit tests.

### Task 1: Add the shared operator semantics domain model

**Files:**
- Create: `src/spec_orch/domain/operator_semantics.py`
- Test: `tests/unit/test_operator_semantics.py`

**Step 1: Write the failing tests**

Add tests that define the minimum canonical objects and serialization:
- `Workspace` carries stable ids plus embedded execution/judgment/learning summaries
- `ExecutionSession` can be normalized from an `ExecutionAttempt`
- `Judgment` can be normalized from an `AcceptanceJudgment`
- `LearningLineage` can represent promoted refs even if the rest of learning remains placeholder-only

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `FAIL` because the module and adapters do not exist yet.

**Step 2: Implement the minimal domain model**

Create canonical operator read models:
- `Workspace`
- `SubjectRef`
- `ExecutionSession`
- `ArtifactEnvelope`
- `EvidenceBundle`
- `Judgment`
- `LearningLineage`
- `PromotedFinding`
- `MemoryEntryRef`
- `EvolutionProposalRef`

Each object should have `to_dict()` and use operator-facing field names from the April 1 protocol docs.

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py -q
```

Expected: `PASS`.

### Task 2: Add normalization adapters and wire intake handoff to them

**Files:**
- Create: `src/spec_orch/services/operator_semantics.py`
- Modify: `src/spec_orch/services/intake_handoff.py`
- Modify: `tests/unit/test_intake_handoff.py`
- Modify: `tests/unit/test_dashboard_launcher.py`

**Step 1: Extend the failing tests**

Add tests for:
- `workspace_from_canonical_issue()` building shared workspace placeholders from a canonical issue
- `build_workspace_handoff()` exposing a canonical `workspace` object while keeping compatibility placeholders
- dashboard intake workspace persisting the shared workspace contract in its handoff payload

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_intake_handoff.py tests/unit/test_dashboard_launcher.py -q
```

Expected: `FAIL` because the adapters and new handoff shape do not exist yet.

**Step 2: Implement the adapters**

Add:
- `workspace_from_canonical_issue()`
- `execution_session_from_attempt()`
- `evidence_bundle_from_attempt()`
- `judgment_from_acceptance_judgment()`

Then update `build_workspace_handoff()` to populate:
- `workspace`
- compatibility `active_execution`
- compatibility `initial_judgment`
- compatibility `learning_lineage`

Do not move runtime creation or judgment ownership into this tranche.

**Step 3: Run the tests**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_intake_handoff.py tests/unit/test_dashboard_launcher.py -q
```

Expected: `PASS`.

### Task 3: Verify integration and lint cleanliness

**Files:**
- Verify only; no new files expected unless import re-exports are needed

**Step 1: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_operator_semantics.py tests/unit/test_intake_handoff.py tests/unit/test_dashboard_launcher.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/domain/operator_semantics.py src/spec_orch/services/operator_semantics.py src/spec_orch/services/intake_handoff.py tests/unit/test_operator_semantics.py tests/unit/test_intake_handoff.py tests/unit/test_dashboard_launcher.py
```

Expected: all pass.

**Step 2: Record tranche outcome**

Summarize:
- which shared operator objects now exist
- which consumers use them
- what remains for the next `SON-370` tranche before `SON-374`
