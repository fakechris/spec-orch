# SpecOrch

**AI-native software delivery orchestration for individuals and small teams.**

SpecOrch solves a core problem in agent-heavy development: when you have many coding agents working in parallel, the bottleneck is no longer writing code — it's **decision bandwidth**, **interface stability**, and **verifiable completion**. SpecOrch provides the missing layers between "I have an idea" and "it's safely merged."

## Philosophy: Five Layers, Not a Linear Pipeline

Traditional dev flows are linear: requirement → issue → code → PR → merge.

In multi-agent development, this breaks down. SpecOrch separates the process into five distinct layers:

| Layer | Purpose | Where it lives |
|-------|---------|---------------|
| **Discussion** | Diverge, brainstorm, explore options | Coding environment / Slack / TUI |
| **Contract** | Freeze the spec — what to build, boundaries, acceptance criteria | `docs/specs/` in GitHub repo |
| **Execution** | Break into waves, assign to agents, track dependencies | Linear issues + ExecutionPlan DAG |
| **Code** | Build, verify, review in isolated worktrees | Git worktrees + Codex/Claude agents |
| **Evidence** | Prove completion — gate, deviations, retrospective | `report.json` / `explain.md` / `deviations.jsonl` |

The key insight:

> **Issue is not the requirement — Spec is the requirement.**
> **Merge is not done — Gate is done.**

## User Story: From Idea to Merged Code

### Step 1: Discuss and Draft a Spec

You start in your coding environment (Cursor, Claude Code) or a Slack thread. Brainstorm with an LLM about what to build, explore trade-offs, discuss architecture. This is the *discussion layer* — it can be messy.

When ready, create a Mission:

```bash
spec-orch mission create "WebSocket Real-time Notifications"
# Creates docs/specs/2026-03-websocket-real-time-notifications/spec.md
```

Edit `spec.md` with the LLM's help: user value, technical scope, acceptance criteria, interface contracts, constraints. Iterate until satisfied.

### Step 2: Approve the Spec

When the spec is solid, freeze it:

```bash
spec-orch mission approve 2026-03-websocket-real-time-notifications
```

From this point forward, `spec.md` is the single source of truth. Linear doesn't own the spec — it only references it.

### Step 3: Generate an Execution Plan

The Scoper LLM reads your spec + codebase structure and produces a wave-based DAG:

```bash
spec-orch plan 2026-03-websocket-real-time-notifications
# Output: 4 waves, 7 work packets
#   wave 0: Contract Freeze (1 packet)
#   wave 1: Scaffold (2 packets)
#   wave 2: Parallel Feature Build (3 packets)
#   wave 3: Integration + QA (1 packet)
```

Waves execute sequentially; work packets within a wave can run in parallel.

### Step 4: Promote to Linear

One command creates Linear issues from the plan:

```bash
spec-orch promote 2026-03-websocket-real-time-notifications
# promoted 7 work packets to execution
#   SON-20: [W0] Define WebSocket message types
#   SON-21: [W1] Scaffold server handler
#   ...
```

Each issue carries: spec section reference, files in scope, acceptance criteria, builder prompt, and dependency links.

### Step 5: Execute (Two Modes)

**One-shot CLI** — you drive it:

```bash
spec-orch run SON-20 --source linear --auto-pr
```

This runs the full pipeline in one command: loads issue → LLM plans questions → LLM self-answers → approves spec → Codex builds → verification (lint/typecheck/test) → review → gate evaluation → creates GitHub PR → writes back to Linear.

**Daemon mode** — fully autonomous:

```bash
spec-orch daemon --config spec-orch.toml --repo-root .
```

Polls Linear for Todo issues, runs `advance_to_completion()` on each, auto-creates PRs, writes back results.

### Step 6: Human Acceptance

You don't re-read every line of AI-generated diff. Instead:

```bash
spec-orch accept-issue SON-20 --accepted-by chris
```

This shows you a **spec compliance checklist** and **deviation summary** — you verify *results against spec*, not code against intuition.

### Step 7: Retrospective

After the mission completes:

```bash
spec-orch retro 2026-03-websocket-real-time-notifications
```

Generates `retrospective.md`: all deviations, failed attempts, key decisions. Knowledge is captured for the next cycle.

## Architecture

```
Five-Layer Architecture
═══════════════════════

Discussion ─── Coding env / Slack / TUI
     │
     ▼
Contract ───── docs/specs/<mission>/spec.md + mission.json
     │
     ▼
Execution ──── ExecutionPlan (DAG/Wave) → Linear Issues
     │
     ▼
Code ───────── RunController → Codex Builder → Verification → Review
     │
     ▼
Evidence ───── Gate → report.json → explain.md → deviations.jsonl → Linear write-back
```

### Object Model

```
Mission / Spec ─────── "Why and what" (approved contract, version-controlled)
    │
ExecutionPlan / DAG ── "How to split" (waves, work packets, dependencies)
    │
WorkPacket / Issue ─── "Atomic task" (one agent, one worktree, one PR)
    │
Run / Evidence ─────── "What happened" (build, verify, review, gate, deviations)
```

### Key Roles

| System | Role |
|--------|------|
| **GitHub repo `docs/specs/`** | Canonical spec — version-controlled, reviewable, agent-readable |
| **Linear** | Execution graph + delegation surface + status truth |
| **Obsidian** | Knowledge plane — research, retro, thinking (Phase 5+) |
| **Orchestrator** | Claim issue → worktree → builder → verification → gate → PR |
| **Gate** | Prove completion — the *only* merge authority |
| **Human** | Final acceptance — verifies results, not diffs |

## Status

SpecOrch is in **dogfood-first (EODF)** mode — the system is used to develop itself.

What works on `main`:

- Five-layer architecture: Discussion → Contract → Execution → Code → Evidence
- `Mission` model with canonical specs in `docs/specs/`
- `ExecutionPlan` / `Wave` / `WorkPacket` DAG with LLM-based scoping
- One-shot `spec-orch run` with LLM self-answering blocking questions
- `advance_to_completion()` for full pipeline automation
- Fixture-driven or Linear-backed issue loading (`IssueSource` protocol)
- Per-issue git worktrees with isolated execution
- Codex builder via `codex exec --json` (`BuilderAdapter` protocol)
- Real verification: ruff, mypy, pytest
- Configurable Gate evaluation with `gate.policy.yaml`
- Daemon mode with full automation: poll → build → gate → PR → Linear write-back
- GitHub PR auto-creation + Gate as commit status check
- Spec deviation tracking (`deviations.jsonl`)
- Retrospective generation (`spec-orch retro`)
- Enhanced acceptance with spec compliance checklist

What is still intentionally incomplete:

- Real Obsidian sync (knowledge plane connector)
- Claude review adapter
- Preview deployment and browser verification
- Slack integration for discussion layer
- Wave-aware scheduling in daemon (dependency ordering)

## Quick Start

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest -q
```

## CLI Reference

### Mission Management (Contract Layer)

```bash
spec-orch mission create "Feature Title"          # Create mission + spec skeleton
spec-orch mission approve <mission-id>             # Freeze spec for execution
spec-orch mission status                           # List all missions
spec-orch mission show <mission-id>                # Print canonical spec
```

### Planning & Promotion (Execution Layer)

```bash
spec-orch plan <mission-id>                        # LLM scoper generates DAG
spec-orch plan-show <mission-id>                   # View wave/packet breakdown
spec-orch promote <mission-id>                     # Create Linear issues from plan
```

### Execution (Code Layer)

```bash
spec-orch run <issue-id> --source linear --auto-pr # Full one-shot pipeline
spec-orch advance <issue-id> --source linear       # Single state transition
spec-orch run-issue <issue-id>                     # Legacy: build + verify + gate
spec-orch daemon --config spec-orch.toml           # Autonomous polling mode
```

### Review & Acceptance (Evidence Layer)

```bash
spec-orch review-issue <id> --verdict pass --reviewed-by <name>
spec-orch accept-issue <id> --accepted-by <name>   # Shows spec compliance first
spec-orch status <id>                               # Current state
spec-orch status --all                              # All issues table
spec-orch explain <id>                              # Gate explanation report
spec-orch retro <mission-id>                        # Mission retrospective
```

### Gate & PR

```bash
spec-orch gate <id> --policy gate.policy.yaml      # Evaluate gate
spec-orch create-pr <id>                           # GitHub PR + Linear write-back
```

### Utilities

```bash
spec-orch config check                             # Validate spec-orch.toml
spec-orch diff <id>                                # Git diff for issue worktree
spec-orch cherry-pick <id>                         # Cherry-pick into current branch
spec-orch watch <id>                               # Real-time activity log
spec-orch logs <id>                                # Complete activity history
```

## Repository Layout

```
src/spec_orch/            CLI, orchestration services, domain models
tests/                    Unit and integration tests (226+)
fixtures/issues/          Local issue fixtures
docs/specs/               Canonical specs per mission
docs/architecture/        System design documents
docs/plans/               Implementation plans and roadmaps
gate.policy.yaml          Configurable gate policy
spec-orch.toml            Daemon + planner configuration
.worktrees/               Local isolated workspaces (gitignored)
```

## Documents

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [P0-Alpha Dogfood Plan](docs/plans/2026-03-08-p0-alpha-dogfood-plan.md)
- [Competitive Analysis & Roadmap](docs/plans/2026-03-10-competitive-analysis-and-roadmap.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
