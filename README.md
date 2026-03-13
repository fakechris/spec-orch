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

Start in your coding environment (Cursor, Claude Code) or a Slack thread. Brainstorm with an LLM about what to build, explore trade-offs, discuss architecture. This is the *discussion layer* — it can be messy.

```bash
spec-orch discuss
# Interactive TUI brainstorming with LLM planner
# Type @freeze when ready to formalise the discussion into a spec
```

Or create a Mission directly:

```bash
spec-orch mission create "WebSocket Real-time Notifications"
# Creates docs/specs/2026-03-websocket-real-time-notifications/spec.md
```

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
spec-orch daemon start --config spec-orch.toml --repo-root .
```

The daemon continuously:
1. Polls Linear for issues in **Ready** state (configurable via `consume_state`)
2. Runs **readiness triage** — rule-based + LLM check on issue completeness; if underspecified, posts clarification questions on Linear and adds `needs-clarification` label
3. Moves to **In Progress** on pickup
4. Executes the build pipeline (Codex build → verification → review → gate)
5. Checks **merge readiness** (`git merge-tree` dry-run, auto-rebase if needed)
6. On success: creates PR, moves to **In Review**
7. **Review loop**: monitors PRs for new commits; when fixes are pushed, re-runs verification + gate
8. On merge: Linear-GitHub App auto-closes the issue to **Done**
9. On failure: adds comment with error details, leaves in **In Progress** for triage

**Mission mode** — execute a full plan:

```bash
spec-orch run-plan 2026-03-websocket-real-time-notifications
# Executes all waves in sequence, packets in parallel
```

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

Discussion ─── CLI TUI / Slack / Linear comments
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

### Key Components

| Component | Role |
|-----------|------|
| **RunController** | Orchestrates the full issue lifecycle: claim → worktree → build → verify → review → gate |
| **ReadinessChecker** | Rule-based + LLM evaluation of issue completeness before execution |
| **CodexExecBuilderAdapter** | Delegates code generation to `codex exec --json` |
| **VerificationService** | Runs lint, typecheck, test, build via subprocess |
| **GateService** | Evaluates merge conditions per `gate.policy.yaml` profiles |
| **ComplianceEngine** | Evaluates agent behaviour against YAML-defined contracts |
| **GitHubPRService** | Creates PRs, checks merge readiness, auto-rebases, tracks review updates |
| **LinearClient** | GraphQL client for issue CRUD, comments, state transitions, labels |
| **PromotionService** | Creates Linear issues from an ExecutionPlan's work packets |
| **ConversationService** | Transport-agnostic brainstorming engine (TUI, Linear, Slack) |
| **DaemonInstaller** | Generates systemd/launchd service files for daemon process management |
| **ParallelRunController** | Executes multi-wave plans with concurrent packet execution |

### Key Roles

| System | Role |
|--------|------|
| **GitHub repo `docs/specs/`** | Canonical spec — version-controlled, reviewable, agent-readable |
| **Linear** | Execution graph + delegation surface + status truth |
| **Orchestrator** | Claim issue → triage → worktree → builder → verification → gate → PR |
| **Gate** | Prove completion — the *only* merge authority |
| **Human** | Final acceptance — verifies results, not diffs |

## Status

SpecOrch is in **dogfood-first (EODF)** mode — the system is used to develop itself.

What works on `main`:

- Five-layer architecture: Discussion → Contract → Execution → Code → Evidence
- `Mission` model with canonical specs in `docs/specs/`
- `ExecutionPlan` / `Wave` / `WorkPacket` DAG with LLM-based scoping
- Interactive brainstorming via `spec-orch discuss` with `@freeze` to spec
- One-shot `spec-orch run` with LLM self-answering blocking questions
- `advance_to_completion()` for full pipeline automation
- Parallel wave execution via `spec-orch run-plan`
- Fixture-driven or Linear-backed issue loading (`IssueSource` protocol)
- Per-issue git worktrees with isolated execution
- Codex builder via `codex exec --json` (`BuilderAdapter` protocol)
- Real verification: ruff, mypy, pytest
- Configurable Gate evaluation with `gate.policy.yaml` (profiles, auto-merge conditions)
- Configurable compliance engine with `compliance.contracts.yaml`
- Daemon mode: poll Ready → readiness triage → build → gate → PR → Linear write-back
- Daemon review loop: detects new commits on PRs, re-runs verification + gate
- Daemon merge readiness: `git merge-tree` dry-run + auto-rebase before PR creation
- Daemon process management: systemd/launchd install, state persistence across restarts
- GitHub PR auto-creation + Gate as commit status check
- Spec deviation tracking (`deviations.jsonl`)
- Retrospective generation (`spec-orch retro`)
- Enhanced acceptance with spec compliance checklist
- Three-tier change management: Full / Standard / Hotfix
- Web dashboard for pipeline visualization

What is still intentionally incomplete:

- Real Obsidian sync (knowledge plane connector)
- AI-assisted merge conflict resolution (SON-68)
- Daemon hotfix mode with priority queue and minimal gate (SON-72)
- Preview deployment and browser verification
- Slack bot for discussion layer

## Quick Start

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
cp .env.example .env   # Add your API tokens
.venv/bin/python -m pytest -q
```

## CLI Reference (49 commands)

### Discussion Layer

```bash
spec-orch discuss                     # Interactive brainstorming TUI
spec-orch discuss list                # List active conversation threads
spec-orch discuss freeze              # Freeze a conversation into a spec
```

### Contract Layer — Missions

```bash
spec-orch mission create "Title"      # Create mission + spec skeleton
spec-orch mission approve <id>        # Freeze spec for execution
spec-orch mission status              # List all missions
spec-orch mission show <id>           # Print canonical spec
```

### Execution Layer — Planning & Promotion

```bash
spec-orch plan <mission-id>           # LLM scoper generates DAG
spec-orch plan-show <mission-id>      # View wave/packet breakdown
spec-orch promote <mission-id>        # Create Linear issues from plan
spec-orch pipeline <mission-id>       # Show EODF pipeline progress (11 stages)
```

### Code Layer — Execution

```bash
spec-orch run <id> --source linear [--auto-pr]  # Full one-shot pipeline
spec-orch run-plan <mission-id>       # Execute plan with parallel waves
spec-orch run-issue <id>              # Build + verify + gate
spec-orch advance <id> --source linear  # Single state transition
spec-orch rerun <id>                  # Re-run verification + gate
```

### Code Layer — Daemon

```bash
spec-orch daemon start --config spec-orch.toml --repo-root .  # Start daemon
spec-orch daemon stop                 # Stop system service
spec-orch daemon status               # Show service + state info
spec-orch daemon install              # Install as systemd/launchd service
```

### Evidence Layer — Review & Acceptance

```bash
spec-orch review-issue <id> --verdict pass --reviewed-by <name>
spec-orch review-pr <id>             # Auto-review PR via GitHub bots
spec-orch accept-issue <id> --accepted-by <name>
spec-orch retro <mission-id>         # Mission retrospective
```

### Evidence Layer — Gate & Compliance

```bash
spec-orch gate evaluate <id>          # Evaluate gate conditions
spec-orch gate show-policy            # Print current gate policy
spec-orch gate list-conditions        # List all gate conditions
spec-orch gate profiles               # List available profiles
spec-orch compliance evaluate         # Evaluate builder events against contracts
spec-orch compliance list-contracts   # List compliance contracts
```

### Inspection & Debugging

```bash
spec-orch status <id>                 # Current run state
spec-orch status --all                # All issues table
spec-orch explain <id>                # Gate explanation report
spec-orch diff <id>                   # Git diff for issue worktree
spec-orch cherry-pick <id>            # Cherry-pick into current branch
spec-orch watch <id>                  # Real-time activity log
spec-orch logs <id>                   # Complete activity history
spec-orch create-pr <id>             # GitHub PR + Linear write-back
spec-orch dashboard                   # Web dashboard
```

### Spec & Questions Management

```bash
spec-orch spec show <id>              # Show spec snapshot
spec-orch spec approve <id>           # Approve spec for build
spec-orch spec draft <id>             # Draft spec from fixture
spec-orch questions list <id>         # List blocking questions
spec-orch questions add <id>          # Add a question
spec-orch questions answer <id>       # Answer with a Decision
spec-orch findings list <id>          # List findings
spec-orch findings add <id>           # Add a finding
spec-orch findings resolve <id>       # Resolve a finding
```

### Configuration

```bash
spec-orch config check                # Validate spec-orch.toml + dependencies
spec-orch plan-to-spec <file>         # Convert plan markdown to fixture JSON
spec-orch --version                   # Show version
```

## Configuration

SpecOrch is configured via `spec-orch.toml`:

```toml
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"
team_key = "SON"

[builder]
adapter = "codex_exec"
codex_executable = "codex"

[planner]
model = "minimax/MiniMax-M1"
api_type = "litellm"
api_key_env = "MINIMAX_API_KEY"

[github]
base_branch = "main"

[daemon]
max_concurrent = 1
consume_state = "Ready"
exclude_labels = ["blocked", "needs-clarification"]
```

Environment variables are loaded automatically from `.env` in the project root.

## Repository Layout

```
src/spec_orch/
  cli.py                 CLI entry point (49 commands)
  domain/
    models.py            Core domain models (Mission, ExecutionPlan, Run, Gate, etc.)
    protocols.py         Adapter protocols (Builder, Planner, IssueSource, etc.)
  services/
    run_controller.py    Main orchestration loop
    daemon.py            Autonomous daemon with triage, review loop, merge check
    readiness_checker.py Rule-based + LLM issue completeness check
    gate_service.py      Configurable gate evaluation
    compliance_engine.py YAML-driven agent behaviour contracts
    github_pr_service.py PR creation, merge readiness, auto-rebase
    linear_client.py     Linear GraphQL API client
    promotion_service.py ExecutionPlan → Linear issues
    conversation_service.py  Transport-agnostic brainstorming engine
    daemon_installer.py  systemd/launchd service file generation
    parallel_run_controller.py  Multi-wave concurrent execution
    codex_exec_builder_adapter.py  Codex exec integration
    verification_service.py  Lint, typecheck, test runner
tests/                   Unit and integration tests (396+)
fixtures/issues/         Local issue fixtures
docs/specs/              Canonical specs per mission
docs/architecture/       System design and policy documents
docs/plans/              Implementation plans and roadmaps
gate.policy.yaml         Gate policy: conditions, profiles, auto-merge rules
compliance.contracts.yaml  Compliance rules for agent behaviour
spec-orch.toml           Daemon, planner, and Linear configuration
.env                     API tokens (gitignored)
.spec_orch_runs/         Per-issue run artifacts (gitignored)
.worktrees/              Isolated git worktrees (gitignored)
```

## Documents

### Current (authoritative)

- [Pipeline Roles and Stages](docs/architecture/pipeline-roles-and-stages.md) — end-to-end flow with roles
- [Change Management Policy](docs/architecture/change-management-policy.md) — three-tier workflow (Full/Standard/Hotfix)
- [Linear API Surface](docs/architecture/linear-api-surface.md) — compatibility contract for Linear replacement
- [Linear PM Convention](docs/specs/linear-pm-convention/spec.md) — daemon consumption protocol
- [Competitive Analysis & Roadmap](docs/plans/2026-03-10-competitive-analysis-and-roadmap.md)

### Historical (early design, kept as decision records)

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [Orchestration Plane Options](docs/architecture/orchestration-plane-options-and-mvp.md)
- [V1 Implementation Plan](docs/plans/2026-03-07-spec-orch-v1-implementation.md)
- [P0-Alpha Dogfood Plan](docs/plans/2026-03-08-p0-alpha-dogfood-plan.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
