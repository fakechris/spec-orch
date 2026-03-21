# SpecOrch

[![CI](https://github.com/fakechris/spec-orch/actions/workflows/ci.yml/badge.svg)](https://github.com/fakechris/spec-orch/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/spec-orch)](https://pypi.org/project/spec-orch/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/spec-orch)](https://pypi.org/project/spec-orch/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**The control plane for spec-driven software delivery.**

> [中文版 README](README.zh.md) | [Project Vision](VISION.md) / [项目愿景](VISION.zh.md)

SpecOrch orchestrates AI coding agents with a spec-first, gate-first, evidence-driven approach. It connects **intent, tasks, execution, verification, and evolution** into a coherent control plane — so you can stop babysitting agents and start operating a delivery system.

**Not a chatbot. Not a multi-agent playground. Not an IDE.**

A control plane that makes software delivery orchestratable, verifiable, and self-improving.

## Core Insights

> **Issue is not the requirement — Spec is the requirement.**
> **Merge is not done — Gate is done.**
> **Orchestration is not static — it evolves with every run.**
> **Prompt is advice — Harness is enforcement.**

## Seven-Plane Architecture

SpecOrch organizes the full delivery lifecycle into seven planes:

```
┌──────────────────────────────────────────────────────┐
│  Evolution    traces → evals → harness improvement   │
├──────────────────────────────────────────────────────┤
│  Control      mission / session / PR / gate ops      │
├──────────────────────────────────────────────────────┤
│  Evidence     findings / tests / review / gate       │
├──────────────────────────────────────────────────────┤
│  Execution    worktree / sandbox / agent adapters    │
├──────────────────────────────────────────────────────┤
│  Harness      context contract / skills / policies   │
├──────────────────────────────────────────────────────┤
│  Task         plan DAG / waves / work packets        │
├──────────────────────────────────────────────────────┤
│  Contract     spec / scope / acceptance / freeze     │
└──────────────────────────────────────────────────────┘
```

| Plane | Purpose |
|-------|---------|
| **Contract** | Freeze the spec — what to build, boundaries, acceptance criteria |
| **Task** | Decompose spec into executable task graph with dependencies |
| **Harness** | Make execution reliable: context contracts, policies, hooks, reactions |
| **Execution** | Run each task in isolated worktree/sandbox with pluggable agents |
| **Evidence** | Prove completion: gate evaluation, findings, deviations, reviews |
| **Control** | Operate the system: missions, sessions, PRs, dashboard |
| **Evolution** | Learn from evidence: evolve prompts, rules, strategies, policies |

See [Seven Planes Architecture](docs/architecture/seven-planes.md) for full codebase mapping.

## User Story: From Idea to Merged Code

### 1. Discuss and Draft a Spec (Contract Plane)

```bash
spec-orch discuss
# Interactive TUI brainstorming — type @freeze when ready
```

Or create a Mission directly:

```bash
spec-orch mission create "WebSocket Real-time Notifications"
spec-orch mission approve websocket-real-time-notifications
```

### 2. Generate an Execution Plan (Task Plane)

```bash
spec-orch plan websocket-real-time-notifications
# Output: 4 waves, 7 work packets
```

Waves execute sequentially; work packets within a wave run in parallel.

### 3. Execute (Execution Plane)

**One-shot CLI:**

```bash
spec-orch run SON-20 --source linear --auto-pr
```

Full pipeline: load issue → plan → build → verify → review → gate → PR → Linear write-back.

**Daemon mode — fully autonomous:**

```bash
spec-orch daemon start --config spec-orch.toml --repo-root .
```

Polls Linear for ready issues → readiness triage → build → verify → gate → PR → review loop.

**Mission mode:**

```bash
spec-orch run-plan websocket-real-time-notifications
```

### 4. Human Acceptance (Evidence Plane)

```bash
spec-orch accept-issue SON-20 --accepted-by chris
```

You verify **results against spec** — a compliance checklist and deviation summary, not raw diffs.

### 5. Retrospective (Evolution Plane)

```bash
spec-orch retro websocket-real-time-notifications
```

Generates retrospective from run evidence. The system learns and improves for next cycle.

## Key Components

### Pluggable Agent Adapters

| Adapter | Agent | Protocol |
|---------|-------|----------|
| `codex_exec` | OpenAI Codex | `codex exec --json` |
| `opencode` | OpenCode | JSONL event stream |
| `claude_code` | Claude Code | stream-json output |
| `droid` | Factory Droid | ACP events |
| `acpx` | 15+ agents | Agent Client Protocol |

Switch agents by changing one line in `spec-orch.toml`:

```toml
[builder]
adapter = "acpx"
agent = "opencode"
model = "minimax/MiniMax-M2.5"
```

### Gate System

Configurable merge conditions with profiles (full / standard / hotfix):

```bash
spec-orch gate evaluate SON-20    # Evaluate all conditions
spec-orch gate show-policy        # Print gate policy
spec-orch explain SON-20          # Human-readable gate report
```

### Self-Evolution Engine

The system improves itself after every run:

```bash
spec-orch evidence summary        # Pattern analysis from historical runs
spec-orch harness synthesize      # Auto-generate compliance rules
spec-orch prompt evolve           # A/B tested prompt variants
spec-orch strategy analyze        # Learned scoper hints
spec-orch policy distill          # Zero-LLM deterministic scripts
```

**Skill Discovery** (SkillCraft-inspired): When `[evolution.skill_evolver] enabled = true` is set in `spec-orch.toml`, the system automatically discovers repeating tool-call patterns from builder telemetry across runs and saves them as reusable `SkillManifest` YAML files. Matched skills are automatically injected into builder context for future runs.

```toml
# spec-orch.toml — enable skill auto-discovery
[evolution.skill_evolver]
enabled = true
```

**How each mechanism activates:**

| Mechanism | Activation | Configuration |
|-----------|-----------|---------------|
| **SkillEvolver** (save) | Config-driven, runs during evolution cycle | `[evolution.skill_evolver] enabled = true` |
| **Skill Runtime** (reuse) | Always active when `.spec_orch/skills/` has YAML files | No config needed |
| **ContextRanker** (hot/cold) | Always active in every `ContextAssembler.assemble()` call | Budget via `NodeContextSpec.max_tokens_budget` |
| **Memory compaction** | Auto-runs every 10th `_finalize_run()` | TTL default 30 days |

## Status

**v0.5.1** — Alpha, dogfood-first (EODF) mode.

The system is used to develop itself and improves itself with each iteration. 1203+ tests, 65+ commands.

What works on `main`:

- Seven-plane architecture with closed-loop evolution (FlowEngine DAGs defined but `run_issue()` uses direct sequencing; unification planned)
- Spec-first approval gate: `run_issue()` requires explicit spec approval by default (`--auto-approve` to bypass)
- Pluggable builder/reviewer adapters (Codex, OpenCode, Claude Code, Droid, ACPX)
- ACPX unified adapter wrapping 15+ agents via Agent Client Protocol
- Fixture or Linear-backed issue loading with configurable issue sources
- Per-issue git worktree isolation
- Configurable verification (lint, typecheck, test, build) per project type
- Gate evaluation with profiles (full / standard / hotfix)
- Compliance engine with YAML-defined agent behavior contracts
- Daemon mode with readiness triage, review loop, merge check, retry
- GitHub PR auto-creation with gate as commit status
- Spec deviation tracking and structured findings
- Three-tier change management (Full / Standard / Hotfix)
- Web dashboard + Rich TUI (TypeScript/React/Ink)
- Mission Control Center with EventBus
- Conductor for progressive formalization
- Cross-session memory with file-backed storage
- Full self-evolution: evidence analysis, harness synthesis, prompt evolution, policy distillation
- `spec-orch init` for project type detection and config generation
- Low-cost model support (MiniMax-M2.5, ~$0.04/run)
- `spec-orch preflight` one-click system health check
- `spec-orch selftest` end-to-end smoke test with fixture issues
- FlowRouter hybrid routing (static rules + LLM-based complexity analysis)
- KnowledgeDistiller: cross-run learning notebook (`.spec_orch/knowledge.md`) (standalone, manual invocation)
- ContextRanker: priority-aware context truncation replacing naive text slicing
- RunProgressSnapshot: pipeline stage checkpointing for daemon retry continuity
- SkillDegradationDetector: routing audit, baseline tracking (standalone, not yet wired into pipeline)
- TraceSampler: online evaluation sampling with configurable rules
- CompactRetentionPriority: architecture-aware context compression
- Atomic JSON writes across all state files (crash-safe daemon)
- Cross-platform file locking for evolution counter (POSIX + Windows)
- LifecycleEvolver protocol: unified 4-phase observe/propose/validate/promote for all 7 evolvers
- SkillEvolver: auto-discovers reusable builder tool-call patterns → SkillManifest YAML (SkillCraft-inspired)
- Skill Runtime: ContextAssembler loads + matches skills by trigger keywords, injects into builder context
- ContextRanker hot/cold separation: learning context (hints, skills, failure samples) included in priority-based budget allocation
- Memory compaction + TTL: episodic memory auto-expires after 30 days, run outcomes consolidated to semantic layer
- Modular CLI: `cli/` package with 8 command submodules replacing single 4092-line file
- LLM JSON output schema validation with fallback + observability events

## Installation

### Quick Start

```bash
# 1. Install
git clone https://github.com/fakechris/spec-orch.git
cd spec-orch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure environment — copy and edit .env
cp .env.example .env
# Edit .env: set SPEC_ORCH_LLM_API_KEY and SPEC_ORCH_LLM_API_BASE
# (see .env.example for provider-specific examples)

# 3. Initialize project config
spec-orch init                    # LLM-first detection (auto fallback to rules)
spec-orch init --offline          # Force rule-based detection
spec-orch init --reconfigure      # Re-detect and overwrite existing config

# 4. Verify everything works
spec-orch config check            # Validate configuration
spec-orch discuss                 # Test LLM connectivity with interactive TUI
```

**Minimum required environment variables** (set in `.env` or export):

| Variable | Purpose | Example |
|----------|---------|---------|
| `SPEC_ORCH_LLM_API_KEY` | LLM provider API key (planner, discuss, triage) | `sk-ant-xxx` or MiniMax key |
| `SPEC_ORCH_LLM_API_BASE` | LLM API endpoint | `https://api.anthropic.com` |
| `SPEC_ORCH_LINEAR_TOKEN` | Linear issue tracking (optional for daemon) | `lin_api_xxx` |

See [`.env.example`](.env.example) for full configuration reference.

### From GitHub via pip / uv

```bash
pip install "spec-orch @ git+https://github.com/fakechris/spec-orch.git"
uv pip install "spec-orch @ git+https://github.com/fakechris/spec-orch.git"
```

### From PyPI

```bash
pip install spec-orch
pip install "spec-orch[all]"
```

### Verify

```bash
spec-orch --version   # 0.5.1
spec-orch config check
```

### Requirements

- **Python 3.11+** (3.11, 3.12, 3.13 tested)
- **Git** (for worktree isolation)
- **Builder CLI** — one of: Codex, OpenCode, Droid, Claude Code, or any ACPX-compatible agent
- **Linear API token** (optional, for issue tracking)
- **LLM API key** (optional, for planning / review / triage)

### Optional Extras

| Extra | Packages | Use case |
|-------|----------|----------|
| `planner` | litellm | `discuss`, `plan`, readiness triage |
| `dashboard` | fastapi, uvicorn | `spec-orch dashboard` |
| `slack` | slack-bolt | Slack discussion adapter |
| `all` | all of the above | Full feature set |
| `dev` | all + pytest, ruff, mypy, build, twine | Development |

## Configuration

SpecOrch is configured via `spec-orch.toml`. Run `spec-orch init` to auto-detect your project and generate config:

```bash
spec-orch init               # LLM-first detection; auto fallback to rules
spec-orch init --offline     # Force rule-based detection
spec-orch init --reconfigure # Re-run detection and overwrite existing config
spec-orch init --force       # Force overwrite existing config
```

`spec-orch init` persists selected detection mode into `[init].detection_mode`
inside `spec-orch.toml` for deterministic future reconfiguration.

See [spec-orch.toml Reference](docs/reference/spec-orch-toml.md) and [AI Config Guide](docs/guides/ai-config-guide.md) for full documentation.

## CLI Reference (65+ commands)

### Contract Plane

```bash
spec-orch discuss                     # Interactive brainstorming TUI
spec-orch mission create "Title"      # Create mission + spec skeleton
spec-orch mission approve <id>        # Freeze spec for execution
spec-orch mission status              # List all missions
spec-orch contract generate <id>      # Generate TaskContract from issue
```

### Task Plane

```bash
spec-orch plan <mission-id>           # LLM scoper generates DAG
spec-orch plan-show <mission-id>      # View wave/packet breakdown
spec-orch promote <mission-id>        # Create Linear issues from plan
spec-orch pipeline <mission-id>       # Show EODF pipeline progress
```

### Execution Plane

```bash
spec-orch run <id> --source linear    # Full one-shot pipeline
spec-orch run <id> --auto-approve     # Skip spec approval, auto-approve
spec-orch run-plan <mission-id>       # Execute plan with parallel waves
spec-orch run-issue <id>              # Build + verify + gate (requires spec approval)
spec-orch run-issue <id> --auto-approve  # Auto-approve spec and run
spec-orch daemon start                # Autonomous daemon mode
```

### Evidence Plane

```bash
spec-orch gate evaluate <id>          # Evaluate gate conditions
spec-orch review-issue <id>           # Review with verdict
spec-orch accept-issue <id>           # Human acceptance
spec-orch explain <id>                # Gate explanation report
spec-orch retro <mission-id>          # Mission retrospective
```

### Control Plane

```bash
spec-orch status <id>                 # Current run state
spec-orch status --all                # All issues table
spec-orch dashboard                   # Web dashboard
spec-orch watch <id>                  # Real-time activity log
spec-orch config check                # Validate configuration
```

### Evolution Plane

```bash
spec-orch evidence summary            # Pattern analysis
spec-orch harness synthesize          # Auto-generate rules
spec-orch prompt evolve               # A/B tested prompts
spec-orch strategy analyze            # Scoper hints
spec-orch policy distill              # Zero-LLM scripts
```

## Documents

### Vision & Architecture

- [Project Vision](VISION.md) / [项目愿景](VISION.zh.md)
- [Seven Planes Architecture](docs/architecture/seven-planes.md)
- [Roadmap & Milestones](docs/plans/roadmap.md)

### Design (Current)

- [Self-Evolution Architecture](docs/specs/self-evolution/spec.md)
- [Pipeline Roles and Stages](docs/architecture/pipeline-roles-and-stages.md)
- [Orchestration Brain Design](docs/architecture/orchestration-brain-design.md)
- [Context Contract Design](docs/architecture/context-contract-design.md)
- [Spec-Contract Integration](docs/architecture/spec-contract-integration.md)
- [Change Management Policy](docs/architecture/change-management-policy.md)
- [SDD Landscape & Positioning](docs/architecture/sdd-landscape-and-positioning.md)
- [Directional Review (Agent Engineering)](docs/architecture/2026-03-19-directional-review.zh.md)

### Reviews

- [Architecture Deep Review (2026-03-20)](docs/reviews/2026-03-20-architecture-deep-review.md)

### Reference & Guides

- [spec-orch.toml Reference](docs/reference/spec-orch-toml.md)
- [AI Config Guide](docs/guides/ai-config-guide.md)
- [EODF with ACPX Guide](docs/guides/eodf-acpx-guide.md)

### Historical (Decision Records)

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [V1 Implementation Plan](docs/plans/2026-03-07-spec-orch-v1-implementation.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
