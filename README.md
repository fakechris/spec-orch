# SpecOrch

SpecOrch is an AI-native software delivery orchestration system for individuals and small teams.

It treats:

- `Linear` as the control plane for deciding what to work on
- `Obsidian` as the knowledge plane for capturing why and how work happened
- `Orchestrator` as the runtime control center
- `Codex`, `Claude`, and browser/mobile agents as execution adapters
- `Spec` and `Gate` as the definition-of-done and mergeability layer

This repository currently contains the initial architecture document and a v1 implementation plan.

## Status

SpecOrch is currently in `prototype-first` mode.

What already works on `main`:

- local fixture-driven issue runs
- per-issue git worktrees
- `task.spec.md`, `progress.md`, `report.json`, `explain.md`
- Codex builder routing through `codex app-server`
- local review and acceptance state transitions
- real verification command execution
- structured telemetry for builder, verification, review, and gate

What is still intentionally incomplete:

- real Linear sync
- real Obsidian sync
- Claude review adapter
- preview deployment and browser verification
- production policy/config management

## MVP Prototype

The repository contains a runnable local Python prototype.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest -q
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root .
```

When `--repo-root` is not a git repository, the command creates a local run workspace under `.spec_orch_runs/SPC-1/` and writes:

- `task.spec.md`
- `progress.md`
- `report.json`

When `--repo-root` points at a git repository, the runner prefers a real issue worktree under `.worktrees/<issue-id>/` and also writes:

- `explain.md`
- `builder_report.json` when the builder adapter runs
- `review_report.json` after a review step
- `acceptance.json` after human acceptance

## CLI Commands

The current prototype exposes these commands:

```bash
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root .
.venv/bin/python -m spec_orch.cli review-issue SPC-1 --repo-root . --verdict pass --reviewed-by claude
.venv/bin/python -m spec_orch.cli accept-issue SPC-1 --repo-root . --accepted-by chris
```

`run-issue` creates or reuses the issue workspace, runs the builder, executes verification, initializes review state, and evaluates the gate.

`review-issue` records the review verdict and recalculates the gate.

`accept-issue` records human acceptance and can move the issue to `mergeable=True` once the other requirements pass.

Issue fixtures can also define real verification commands:

```json
{
  "verification_commands": {
    "lint": ["{python}", "-c", "print('lint ok')"],
    "typecheck": ["{python}", "-c", "print('type ok')"],
    "test": ["{python}", "-m", "pytest", "-q"],
    "build": ["{python}", "-c", "print('build ok')"]
  }
}
```

`{python}` resolves to the current virtual environment interpreter, so verification runs inside the same project environment as the CLI.

Issue fixtures can also define a `builder_prompt` for the builder adapter:

```json
{
  "builder_prompt": "Implement the issue in this workspace."
}
```

SpecOrch now routes builder work to Codex through the local `codex app-server` harness by default. The orchestrator starts a Codex thread over stdio, sends a builder turn, captures agent message deltas plus plan updates, and writes them into `builder_report.json`.

You can point SpecOrch at an explicit Codex executable:

```bash
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root . --codex-executable /path/to/codex
```

If the Codex harness transport cannot be started, SpecOrch falls back to the existing `pi_codex` adapter for compatibility:

```bash
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root . --codex-executable /missing/codex --pi-executable /path/to/pi
```

Both builder paths inject `SPEC_ORCH_BUILDER_AGENT=codex`. The active adapter is recorded in `builder_report.json` and the top-level `report.json`.

## Telemetry

Each issue workspace contains a `telemetry/` directory. Current artifacts include:

- `events.jsonl`: high-level lifecycle events from run controller, builder, verification, review, and gate
- `raw_harness_in.jsonl`: raw JSON-RPC messages sent to Codex
- `raw_harness_out.jsonl`: raw JSON-RPC messages received from Codex
- `raw_harness_err.log`: Codex stderr
- `incoming_events.jsonl`: parsed incoming harness messages with `observed_at`, `kind`, and short excerpts
- `harness_state.json`: current liveness snapshot with `run_id`, `thread_id`, `turn_id`, timeout policy, and last protocol/output/progress excerpts

This is the current debugging surface for long-running Codex turns.

## Development Workflow

Recommended local workflow:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest -q
```

For isolated feature work, use git worktrees under `.worktrees/`.

For builder dogfooding, point SpecOrch at a local Codex CLI installation:

```bash
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root . --codex-executable /path/to/codex
```

## Repository Layout

- `src/spec_orch/`: CLI, orchestration services, domain models
- `tests/`: unit and integration tests
- `fixtures/issues/`: local issue fixtures used by the prototype
- `docs/architecture/`: system design and architecture notes
- `docs/plans/`: implementation plans
- `.worktrees/`: local isolated workspaces, intentionally ignored by git

## Documents

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [v1 Implementation Plan](docs/plans/2026-03-07-spec-orch-v1-implementation.md)
- [P0-Alpha Dogfood Plan](docs/plans/2026-03-08-p0-alpha-dogfood-plan.md)
- [P0-Alpha Issue Backlog](docs/plans/2026-03-08-p0-alpha-issue-backlog.md)
- [Orchestration Options and MVP Dogfooding](docs/architecture/orchestration-plane-options-and-mvp.md)
- [Observability v1 Design](docs/architecture/observability-v1-design.md)

## Current Scope

The initial goal is to prove a reliable, auditable, agent-native delivery loop:

1. Pull work from Linear.
2. Create an isolated execution workspace per issue.
3. Generate task spec and progress artifacts.
4. Route implementation to Codex.
5. Route review to Claude.
6. Run verification and optional preview checks.
7. Write structured results back to Linear, PRs, and local audit storage.
8. Compute `Mergeable` through a Gate layer instead of trusting any single agent.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
