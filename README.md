# SpecOrch

SpecOrch is an AI-native software delivery orchestration system for individuals and small teams.

It treats:

- `Linear` as the control plane for deciding what to work on
- `Obsidian` as the knowledge plane for capturing why and how work happened
- `Orchestrator` as the runtime control center
- `Codex`, `Claude`, and browser/mobile agents as execution adapters
- `Spec` and `Gate` as the definition-of-done and mergeability layer

This repository currently contains the initial architecture document and a v1 implementation plan.

## MVP Prototype

The current feature branch contains a runnable local prototype in Python.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root .
```

The command creates a local run workspace under `.spec_orch_runs/SPC-1/` and writes:

- `task.spec.md`
- `progress.md`
- `report.json`

When `--repo-root` points at a git repository, the runner now prefers a real issue worktree under `.worktrees/<issue-id>/` and also writes:

- `explain.md`
- `builder_report.json` when the builder adapter runs

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

Issue fixtures can also define a `builder_prompt` for the `pi` builder adapter:

```json
{
  "builder_prompt": "Implement the issue in this workspace."
}
```

The CLI uses `pi` by default, or you can point it at an explicit executable:

```bash
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root .
.venv/bin/python -m spec_orch.cli run-issue SPC-1 --repo-root . --pi-executable /path/to/pi
```

## Documents

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [v1 Implementation Plan](docs/plans/2026-03-07-spec-orch-v1-implementation.md)
- [Orchestration Options and MVP Dogfooding](docs/architecture/orchestration-plane-options-and-mvp.md)

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
