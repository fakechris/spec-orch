# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-10

### Added

- **Packaging**: Standard PyPI distribution with `pip install spec-orch` and `uv` support
- **Homebrew**: Formula for `brew install spec-orch`
- **CI/CD**: GitHub Actions workflows for lint, test (3.11/3.12/3.13 × Ubuntu/macOS), build, and PyPI publishing
- **Python 3.11+ compatibility**: Lowered minimum from 3.13 to 3.11 for broader adoption
- **Daemon mode**: Autonomous polling of Linear issues with readiness triage, review loop, and merge readiness checks
- **Readiness triage**: Rule-based + LLM evaluation of issue completeness before execution
- **Review loop**: Daemon detects new commits on PRs and re-runs verification + gate
- **Merge readiness**: `git merge-tree` dry-run + auto-rebase before PR creation
- **Daemon process management**: systemd/launchd installer with state persistence
- **Configurable gate evaluation**: `gate.policy.yaml` with profiles and auto-merge conditions
- **Compliance engine**: YAML-driven agent behaviour contracts
- **Parallel wave execution**: `spec-orch run-plan` executes multi-wave plans with concurrent packets
- **Three-tier change management**: Full / Standard / Hotfix policy with branch protection
- **GitHub PR service**: Auto-create PRs, check mergeability, post gate status
- **Remote discussion adapters**: Linear and Slack conversation adapters
- **Web dashboard**: FastAPI-based pipeline visualization

### Changed

- `typer` version constraint relaxed from `>=0.24,<0.25` to `>=0.9` for broader compatibility
- `httpx` minimum lowered from `>=0.28` to `>=0.27`
- `pytest` minimum lowered from `>=9,<10` to `>=8`
- Project description updated from "MVP prototype" to full product description
- README fully rewritten with comprehensive CLI reference, architecture, and installation guide

## [0.1.0] - 2026-03-07

### Added

- Initial implementation with five-layer architecture
- Mission model with canonical specs in `docs/specs/`
- ExecutionPlan / Wave / WorkPacket DAG with LLM-based scoping
- Interactive brainstorming via `spec-orch discuss` with `@freeze`
- One-shot `spec-orch run` pipeline
- Fixture-driven or Linear-backed issue loading
- Per-issue git worktrees with isolated execution
- Codex builder via `codex exec --json`
- Verification: ruff, mypy, pytest
- Basic gate evaluation
- Spec deviation tracking
- Retrospective generation

[0.2.0]: https://github.com/fakechris/spec-orch/releases/tag/v0.2.0
[0.1.0]: https://github.com/fakechris/spec-orch/releases/tag/v0.1.0
