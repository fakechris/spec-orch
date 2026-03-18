# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-03-18

### Added

- **Context Contract System**: Structured `ContextBundle` (TaskContext / ExecutionContext / LearningContext) replaces ad-hoc prompt assembly across all LLM nodes
- **ContextAssembler**: Dynamic context assembly for ReadinessChecker, Planner, Scoper, and IntentClassifier — each node now receives structured, budget-aware context
- **ArtifactManifest**: Standardized artifact cataloguing with downstream consumption by evolvers
- **EvolutionTrigger integration**: Automatic evolution cycle after each run (configurable via `[evolution]` in spec-orch.toml)
- **Daemon resilience**: Restart recovery (in_progress persistence), exponential backoff retry, dead letter queue, hotfix mode (skip triage for P0/hotfix/urgent labels)
- **Task Contract automation**: `TaskContract` schema with YAML serialization, `generate-task-contract` CLI, automatic risk assessment (low/medium/high/critical)
- **3 new CLI commands**: `contract generate`, `contract validate`, `contract assess-risk`
- **35+ new unit tests** covering context integration, daemon resilience, and contract automation

### Changed

- `ReadinessChecker.check()` accepts optional `ContextBundle` for richer LLM triage
- `LiteLLMPlannerAdapter.plan()` and `answer_questions()` accept optional `context` parameter
- `LiteLLMScoperAdapter.scope()` accepts optional `context` with scoper hints and failure samples
- `classify_intent()` accepts optional `context` for issue-aware classification
- `EvolutionTrigger` accepts `latest_workspace` to read artifact manifests
- `RunController._finalize_run` triggers evolution cycle when configured
- `DaemonConfig` adds `max_retries`, `retry_base_delay_seconds`, `hotfix_labels`
- Daemon state now persists `retry_counts`, `dead_letter`, `in_progress` sets

## [0.3.0] - 2026-03-14

### Added

- **Self-Evolution Architecture**: Closed-loop improvement inspired by the AutoHarness paper
- **EvidenceAnalyzer**: Aggregates historical run data (success rates, failure patterns, deviation files) into pattern summaries
- **Evidence injection**: Historical context automatically injected into Scoper and ReadinessChecker LLM prompts
- **Dynamic `within_boundaries`**: Gate condition now reflects actual deviation detection (no longer hard-coded)
- **HarnessSynthesizer**: LLM-driven generation of candidate compliance rules from observed failure patterns
- **RuleValidator**: Back-tests candidate rules against historical builder events; auto-merges survivors into `compliance.contracts.yaml`
- **PromptEvolver**: Versioned builder prompt history with A/B testing framework and auto-promotion
- **PlanStrategyEvolver**: Analyzes plan outcomes to generate evidence-based scoper hints for better mission decomposition
- **PolicyDistiller**: Converts recurring tasks into deterministic Python scripts that execute without LLM calls
- **16 new CLI commands**: `evidence summary`, `harness {synthesize,validate,apply}`, `prompt {init,status,evolve,compare,promote,auto-promote}`, `strategy {status,analyze,inject-preview}`, `policy {list,candidates,distill,run}`

### Changed

- `brainstorm()` now respects caller-provided system prompts instead of always prepending a default
- `EvidenceAnalyzer` exposes public methods (`collect_run_dirs`, `read_report`, `read_deviations`)
- `LiteLLMScoperAdapter` accepts `scoper_hints` parameter alongside `evidence_context`
- `deviation_service` provides `overwrite_deviations()` for idempotent persistence
- Project description updated to "Self-evolving AI software delivery orchestration"

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

[0.3.0]: https://github.com/fakechris/spec-orch/releases/tag/v0.3.0
[0.2.0]: https://github.com/fakechris/spec-orch/releases/tag/v0.2.0
[0.1.0]: https://github.com/fakechris/spec-orch/releases/tag/v0.1.0
