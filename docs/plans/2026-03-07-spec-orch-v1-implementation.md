# SpecOrch v1 Implementation Plan

> **Historical Document (2026-03-07).** This was the initial implementation
> plan. The directory structure (`adapters/`, `workflows/`, `storage/`)
> and tooling (`codex app-server`) described here were superseded during
> development. See [README](../../README.md) for the current project
> structure and CLI commands.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first working SpecOrch loop that can pick a Linear issue, create an isolated workspace, prepare task artifacts, run builder and reviewer adapters, aggregate verification results, and compute `Mergeable`.

**Architecture:** Implement SpecOrch as a single-service orchestrator with a small domain model and adapter interfaces. Keep v1 local-first: file-backed state where appropriate, git worktree isolation, explicit workflow artifacts, and structured output contracts instead of deep platform abstractions.

**Tech Stack:** Python 3.12+, `typer` or `click` for CLI, `pydantic` for typed models, `httpx` for APIs, `pytest` for tests, local markdown and JSON artifacts, git worktree commands, adapter wrappers for Codex, Claude, and Playwright.

## Implementation Principles

- Build the smallest reliable closed loop.
- Keep state transitions explicit and testable.
- Prefer file-backed artifacts before adding databases.
- Separate orchestration policy from adapter-specific behavior.
- Make gate evaluation deterministic and auditable.

## Proposed Repository Layout

```text
spec-orch/
├── README.md
├── docs/
│   ├── architecture/
│   └── plans/
├── src/spec_orch/
│   ├── cli.py
│   ├── config.py
│   ├── domain/
│   ├── services/
│   ├── adapters/
│   ├── workflows/
│   └── storage/
├── tests/
│   ├── unit/
│   └── integration/
└── templates/
    ├── task.spec.md
    ├── progress.md
    ├── review_report.md
    └── explain_report.md
```

## Milestones

1. Create the project skeleton and test harness.
2. Model issue state, task artifacts, and gate inputs.
3. Implement local workspace management with git worktrees.
4. Implement artifact generation and workflow state transitions.
5. Add builder, reviewer, and verifier adapter contracts with local stubs.
6. Add verification aggregation and gate evaluation.
7. Add write-back interfaces for Linear and PR comments.
8. Run an end-to-end local demo with a fixture issue.

### Task 1: Bootstrap the Python project

**Files:**
- Create: `pyproject.toml`
- Create: `src/spec_orch/__init__.py`
- Create: `src/spec_orch/cli.py`
- Create: `tests/unit/test_cli_smoke.py`

**Step 1: Write the failing test**

```python
from typer.testing import CliRunner

from spec_orch.cli import app


def test_cli_help_shows_core_commands():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run-issue" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_smoke.py -v`
Expected: FAIL because the package and CLI do not exist yet.

**Step 3: Write minimal implementation**

- Add packaging metadata and dependencies.
- Add a Typer app with placeholder commands:
  - `run-issue`
  - `draft-spec`
  - `evaluate-gate`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_smoke.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml src/spec_orch/__init__.py src/spec_orch/cli.py tests/unit/test_cli_smoke.py
git commit -m "chore: bootstrap spec-orch python cli"
```

### Task 2: Model workflow states and domain objects

**Files:**
- Create: `src/spec_orch/domain/models.py`
- Create: `src/spec_orch/domain/states.py`
- Create: `tests/unit/domain/test_models.py`

**Step 1: Write the failing test**

```python
from spec_orch.domain.models import IssueContext, GateInput
from spec_orch.domain.states import WorkflowState


def test_issue_context_tracks_required_fields():
    issue = IssueContext(
        issue_id="SPC-1",
        title="Demo",
        repo="demo-repo",
        state=WorkflowState.TRIAGED,
    )
    assert issue.issue_id == "SPC-1"
    assert issue.state is WorkflowState.TRIAGED


def test_gate_input_defaults_to_not_mergeable():
    gate = GateInput()
    assert gate.mergeable is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_models.py -v`
Expected: FAIL because domain models do not exist yet.

**Step 3: Write minimal implementation**

- Define workflow states as an enum.
- Define typed models for issue context, workspace context, verification summary, review verdict, and gate input.
- Keep mergeability derived rather than manually toggled where possible.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/domain/models.py src/spec_orch/domain/states.py tests/unit/domain/test_models.py
git commit -m "feat: add workflow domain models"
```

### Task 3: Add task artifact templates and rendering

**Files:**
- Create: `templates/task.spec.md`
- Create: `templates/progress.md`
- Create: `src/spec_orch/services/artifact_service.py`
- Create: `tests/unit/services/test_artifact_service.py`

**Step 1: Write the failing test**

```python
from spec_orch.services.artifact_service import ArtifactService


def test_artifact_service_renders_task_spec(tmp_path):
    service = ArtifactService(template_dir="templates")
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    result = service.write_task_spec(
        out_dir=out_dir,
        issue_title="Add merge gate",
        issue_id="SPC-3",
    )

    assert result.exists()
    assert "Add merge gate" in result.read_text()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_artifact_service.py -v`
Expected: FAIL because the service and templates do not exist.

**Step 3: Write minimal implementation**

- Create markdown templates for `task.spec` and `progress.md`.
- Implement simple template rendering with explicit placeholders.
- Ensure the renderer writes deterministic artifact paths.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_artifact_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add templates/task.spec.md templates/progress.md src/spec_orch/services/artifact_service.py tests/unit/services/test_artifact_service.py
git commit -m "feat: add task artifact generation"
```

### Task 4: Implement workspace management with git worktrees

**Files:**
- Create: `src/spec_orch/services/workspace_service.py`
- Create: `tests/integration/test_workspace_service.py`

**Step 1: Write the failing test**

```python
from spec_orch.services.workspace_service import WorkspaceService


def test_workspace_service_computes_issue_workspace_path(tmp_path):
    service = WorkspaceService(repo_root=tmp_path)
    workspace = service.workspace_path(issue_id="SPC-4")
    assert workspace.name == "SPC-4"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_workspace_service.py -v`
Expected: FAIL because the service does not exist.

**Step 3: Write minimal implementation**

- Compute deterministic worktree paths by issue ID.
- Wrap git worktree commands behind a service boundary.
- Return structured workspace metadata rather than raw shell output.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_workspace_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/workspace_service.py tests/integration/test_workspace_service.py
git commit -m "feat: add workspace management"
```

### Task 5: Define adapter contracts and local stubs

**Files:**
- Create: `src/spec_orch/adapters/base.py`
- Create: `src/spec_orch/adapters/codex_adapter.py`
- Create: `src/spec_orch/adapters/claude_adapter.py`
- Create: `src/spec_orch/adapters/playwright_adapter.py`
- Create: `tests/unit/adapters/test_adapter_contracts.py`

**Step 1: Write the failing test**

```python
from spec_orch.adapters.base import TaskType
from spec_orch.adapters.codex_adapter import CodexAdapter


def test_codex_adapter_handles_implementation_tasks():
    adapter = CodexAdapter()
    assert adapter.can_handle(TaskType.IMPLEMENTATION) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/adapters/test_adapter_contracts.py -v`
Expected: FAIL because adapter contracts do not exist.

**Step 3: Write minimal implementation**

- Define the common adapter interface.
- Add task type enums.
- Implement stub adapters that return structured placeholder artifacts and verdicts.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/adapters/test_adapter_contracts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/adapters/base.py src/spec_orch/adapters/codex_adapter.py src/spec_orch/adapters/claude_adapter.py src/spec_orch/adapters/playwright_adapter.py tests/unit/adapters/test_adapter_contracts.py
git commit -m "feat: add agent adapter contracts"
```

### Task 6: Implement verification aggregation and gate logic

**Files:**
- Create: `src/spec_orch/services/gate_service.py`
- Create: `tests/unit/services/test_gate_service.py`

**Step 1: Write the failing test**

```python
from spec_orch.services.gate_service import GateService
from spec_orch.domain.models import GateInput, ReviewSummary, VerificationSummary


def test_gate_service_marks_mergeable_only_when_all_requirements_pass():
    service = GateService()
    gate = GateInput(
        spec_exists=True,
        spec_approved=True,
        within_boundaries=True,
        verification=VerificationSummary(all_passed=True),
        review=ReviewSummary(verdict="pass"),
        human_acceptance=True,
    )
    result = service.evaluate(gate)
    assert result.mergeable is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_gate_service.py -v`
Expected: FAIL because the service does not exist yet.

**Step 3: Write minimal implementation**

- Implement deterministic mergeability evaluation.
- Return an explainable verdict object with failed conditions listed.
- Keep web preview checks conditional rather than globally required.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_gate_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/gate_service.py tests/unit/services/test_gate_service.py
git commit -m "feat: add merge gate evaluation"
```

### Task 7: Add orchestration flow for a local fixture issue

**Files:**
- Create: `src/spec_orch/services/run_controller.py`
- Create: `src/spec_orch/storage/file_store.py`
- Create: `tests/integration/test_run_controller.py`

**Step 1: Write the failing test**

```python
from spec_orch.services.run_controller import RunController


def test_run_controller_executes_local_issue_fixture(tmp_path):
    controller = RunController.for_local_demo(tmp_path)
    result = controller.run_issue(issue_id="SPC-7")
    assert result.issue_id == "SPC-7"
    assert result.state.value in {"self_verified", "review_pending", "preview_ready", "acceptance_pending", "mergeable"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_run_controller.py -v`
Expected: FAIL because the orchestration flow does not exist.

**Step 3: Write minimal implementation**

- Build a local-only run path using fixture issue data.
- Sequence: context build, workspace prep, artifact generation, builder run, reviewer run, verifier run if applicable, gate evaluation.
- Persist artifacts and run reports in a file store.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_run_controller.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/run_controller.py src/spec_orch/storage/file_store.py tests/integration/test_run_controller.py
git commit -m "feat: add local orchestration flow"
```

### Task 8: Add external sync boundaries

**Files:**
- Create: `src/spec_orch/adapters/linear_adapter.py`
- Create: `src/spec_orch/adapters/pr_adapter.py`
- Create: `tests/unit/adapters/test_sync_adapters.py`

**Step 1: Write the failing test**

```python
from spec_orch.adapters.linear_adapter import LinearAdapter


def test_linear_adapter_builds_state_update_payload():
    adapter = LinearAdapter(api_key="demo")
    payload = adapter.build_state_update(issue_id="SPC-8", state="review_pending")
    assert payload["issue_id"] == "SPC-8"
    assert payload["state"] == "review_pending"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/adapters/test_sync_adapters.py -v`
Expected: FAIL because sync adapters do not exist.

**Step 3: Write minimal implementation**

- Implement payload builders first.
- Keep transport calls behind small methods that can be mocked later.
- Avoid building full API clients until the payload contracts are stable.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/adapters/test_sync_adapters.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spec_orch/adapters/linear_adapter.py src/spec_orch/adapters/pr_adapter.py tests/unit/adapters/test_sync_adapters.py
git commit -m "feat: add sync adapter boundaries"
```

### Task 9: Add a demo workflow and repository documentation

**Files:**
- Modify: `README.md`
- Create: `docs/workflows/local-demo.md`
- Create: `tests/unit/test_readme_references.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_readme_mentions_local_demo_workflow():
    readme = Path("README.md").read_text()
    assert "local demo" in readme.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_readme_references.py -v`
Expected: FAIL because the README does not yet describe the demo workflow.

**Step 3: Write minimal implementation**

- Expand the README with setup and a local demo walkthrough.
- Document the demo issue run in `docs/workflows/local-demo.md`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_readme_references.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/workflows/local-demo.md tests/unit/test_readme_references.py
git commit -m "docs: add local demo workflow"
```

## Verification Checklist

Before calling v1 usable, run:

- `pytest -q`
- `python -m spec_orch.cli --help`
- local fixture issue run through `run-issue`
- gate evaluation against both passing and failing fixture inputs
- manual review of generated markdown artifacts and reports

## Open Questions to Resolve During Implementation

- Should the first version use `typer` or `click`?
- Should local run history stay file-backed or move to SQLite early?
- How much of the `Linear` API should be abstracted in v1 versus kept as payload builders plus thin transport?
- Should preview verification be a synchronous step or a poll-based state transition?

## Suggested Execution Order

1. Complete Tasks 1 through 3 to establish package, models, and artifacts.
2. Complete Tasks 4 through 6 to establish workspace control and mergeability.
3. Complete Tasks 7 and 8 to wire orchestration and external boundaries.
4. Complete Task 9 to document and demo the workflow.
5. Run the verification checklist and then request code review.
