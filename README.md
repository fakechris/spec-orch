# SpecOrch

SpecOrch is an AI-native software delivery orchestration system for individuals and small teams.

It treats:

- `Linear` as the control plane for deciding what to work on
- `Obsidian` as the knowledge plane for capturing why and how work happened
- `Orchestrator` as the runtime control center
- `Codex`, `Claude`, and browser/mobile agents as execution adapters
- `Spec` and `Gate` as the definition-of-done and mergeability layer

## Status

SpecOrch is in **dogfood-first (EODF)** mode — the system is used to develop itself.

What works on `main`:

- fixture-driven or Linear-backed issue loading (`IssueSource` protocol)
- per-issue git worktrees
- `task.spec.md`, `progress.md`, `report.json`, `explain.md`
- Codex builder via `codex exec --json` (`BuilderAdapter` protocol)
- local review and acceptance state transitions
- real verification command execution (ruff, mypy, pytest)
- configurable Gate evaluation with `gate.policy.yaml`
- daemon mode with Linear polling, lockfile, graceful shutdown
- Linear write-back (explain summary + state updates)
- GitHub PR auto-creation + Gate as commit status check
- structured telemetry for builder, verification, review, and gate

What is still intentionally incomplete:

- real Obsidian sync
- Claude review adapter
- preview deployment and browser verification

## Quick Start

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest -q
```

## CLI Commands

### Core workflow

```bash
# Run an issue through the pipeline (fixture-based)
spec-orch run-issue SPC-1 --repo-root .

# Review and accept
spec-orch review-issue SPC-1 --repo-root . --verdict pass --reviewed-by claude
spec-orch accept-issue SPC-1 --repo-root . --accepted-by chris

# Inspect results
spec-orch status SPC-1 --repo-root .
spec-orch explain SPC-1 --repo-root .
spec-orch diff SPC-1 --repo-root .
```

### Gate and PR

```bash
# Evaluate gate with current policy
spec-orch gate SPC-1 --repo-root . --policy gate.policy.yaml
spec-orch gate --show-policy

# Create GitHub PR with gate status
spec-orch create-pr SPC-1 --repo-root .
```

### Daemon mode

```bash
# Poll Linear for issues and process automatically
spec-orch daemon --config spec-orch.toml --repo-root .
```

### Semi-auto EODF workflow

When `builder_prompt` is `null` in a fixture, the builder step is skipped. This allows manual coding + automated verification/gate — the semi-auto EODF loop:

```bash
spec-orch run-issue SPC-BOOT-1 --repo-root .
# ... make code changes manually ...
spec-orch review-issue SPC-BOOT-1 --repo-root . --verdict pass --reviewed-by chris
spec-orch accept-issue SPC-BOOT-1 --repo-root . --accepted-by chris
spec-orch gate SPC-BOOT-1 --repo-root .
spec-orch create-pr SPC-BOOT-1 --repo-root .
```

## Issue Fixtures

Issue fixtures live in `fixtures/issues/<issue-id>.json`. They support:

- `builder_prompt`: prompt for the builder adapter (`null` to skip builder)
- `verification_commands`: real commands to run (`{python}` resolves to venv interpreter)
- `acceptance_criteria`: structured acceptance checklist
- `context`: architecture notes, files to read, constraints

## Architecture

```
spec-orch daemon / CLI
  └── RunController
        ├── IssueSource (Protocol)
        │     ├── FixtureIssueSource
        │     └── LinearIssueSource
        ├── WorkspaceService → git worktree
        ├── ArtifactService → task.spec.md, progress.md, explain.md
        ├── BuilderAdapter (Protocol)
        │     └── CodexExecBuilderAdapter (codex exec --json)
        ├── VerificationService → ruff, mypy, pytest
        ├── ReviewAdapter → review_report.json
        ├── GateService → configurable multi-condition gate
        ├── TelemetryService → events.jsonl
        └── WritebackService
              ├── LinearWriteBackService
              └── GitHubPRService
```

## Telemetry

Each issue workspace contains a `telemetry/` directory with `events.jsonl` and builder-specific artifacts (`incoming_events.jsonl`).

## Repository Layout

- `src/spec_orch/`: CLI, orchestration services, domain models
- `tests/`: unit and integration tests
- `fixtures/issues/`: local issue fixtures
- `docs/`: architecture, plans, reviews
- `gate.policy.yaml`: configurable gate policy
- `spec-orch.toml`: daemon configuration
- `.worktrees/`: local isolated workspaces (gitignored)

## Documents

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [P0-Alpha Dogfood Plan](docs/plans/2026-03-08-p0-alpha-dogfood-plan.md)
- [Competitive Analysis & Roadmap](docs/plans/2026-03-10-competitive-analysis-and-roadmap.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
