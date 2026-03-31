# SpecOrch

**The control plane for spec-driven software delivery.**

> [中文版](VISION.zh.md)

---

SpecOrch is not a chatbot that writes code for you.
It is not another generic multi-agent framework.
It is not an AI IDE replacement.

**SpecOrch is a software delivery control plane.**

It unifies the scattered process of issue tracking, spec writing, agent execution, code review, and merge gating into a single system anchored by **Specs**, proven by **Evidence**, enforced by **Gates**, and improved by **Evolution**.

Our goal is not to make agents look smarter.
Our goal is to make software delivery **orchestratable, verifiable, operable, and evolvable**.

---

## Why SpecOrch Exists

Most AI development tools today solve one problem: "how to get a model to write more code."

But real software delivery is never just about code generation. The hard parts are:

- **Requirements drift** without a frozen, authoritative definition
- **Agent execution is unstable** — non-repeatable, non-traceable
- **PRs get merged** without anyone truly knowing if they meet the original intent
- **Reviews focus on diffs**, missing behavior, risk, deviations, and evidence
- **Prompts grow longer**, systems get more brittle, and nobody can explain why something succeeded or failed

These problems cannot be solved by adding another agent.
They require a higher-order system — one that connects **intent, tasks, execution, verification, and evolution** into a coherent control plane.

**That is where SpecOrch sits.**

---

## Our Thesis

### 1. The spec is the requirement

Issues are not requirements. Chat logs are not requirements. PRs are not requirements.

**The frozen Spec is the single source of truth for each delivery cycle.**

Everything in SpecOrch — execution, verification, review, evolution — anchors to the Spec. An agent without an anchor is just expensive improvisation.

### 2. Merge is not done — Gate is done

Code being generated does not mean work is complete. A PR being merged does not mean the goal was achieved.

**Completion is defined by evidence, not by activity.**

In SpecOrch, the real "done" comes from the Gate: acceptance criteria met, verification passed, deviations explained, risk assessed, evidence sufficient.

### 3. Orchestration before multi-agent

The industry loves talking about multi-agent systems. But most real workflows are orchestration:

- One brain makes decisions
- Multiple workers execute independent tasks
- Tasks connect through structured inputs and outputs
- A parent aggregates, verifies, and decides

**SpecOrch defaults to orchestration-first.** We only upgrade to richer coordination when task dependencies, role negotiation, and shared state genuinely demand it.

### 4. Prompt is advice — Harness is enforcement

Prompts matter, but prompts are not systems.

If a process must be reliably executed, it cannot live only in a prompt. It must be encoded as scripts, policies, gates, hooks, reactions, and runtime rules.

**SpecOrch's core is not "how to write better prompts." It is "how to turn critical execution logic into system-level rails."**

### 4b. Agent-First decisions — LLM where context matters

Every decision point in a delivery system falls into one of three layers:

- **Skeleton**: State machines, protocols, safety checks — must be deterministic, never change at runtime.
- **Configuration**: Thresholds, timeouts, tool names — externalized to `spec-orch.toml`, editable by humans.
- **Intelligence**: Project detection, toolchain selection, verification strategy, readiness judgment — requires understanding the project to decide correctly.

Most orchestration systems hardcode "intelligence" decisions as "skeleton." This makes the system brittle: it only works for the exact scenario the developer anticipated.

**SpecOrch takes an Agent-First approach**: intelligence decisions are made by an LLM at initialization time, materialized as configuration, and evolved through run evidence. The skeleton stays stable. The config adapts. The intelligence learns.

This means `spec-orch init` reads your project files, understands your build system, and generates the right verification commands — whether you use pytest or make, ruff or eslint, cargo or gradle. No hardcoded language profiles.

### 5. Context is a governed contract

Context is not a blob of prompt text. It should be designed, constrained, and layered:

- **Project-level**: long-lived rules and conventions
- **Spec-level**: boundaries and goals for this delivery
- **Task-level**: inputs and outputs for a specific work packet
- **Session-level**: transient state during execution
- **Message-level**: immediate supplements for the current turn

Without context governance, agents rely on accidental memory. Without context boundaries, systems get expensive, slow, and fragile.

### 6. Evidence is the memory of the system

A system's real memory is not chat history. It is structured evidence: decisions, diffs, findings, test results, deviations, gate outcomes, retrospectives, run traces.

These artifacts are not by-products. They are the foundation for learning, explanation, and self-correction.

**Without evidence, evolution is superstition. With evidence, evolution becomes engineering.**

### 7. Evolve the harness, not just the prompt

SpecOrch is not a prompt optimizer. It is an orchestration system that learns.

What we actually optimize includes: context assembly, task decomposition, skill loading, policy extraction, review structure, gate thresholds, runtime reactions, tool surfaces, and execution recipes.

Prompts evolve too — but prompts are just one knob in the harness.

---

## The Seven Planes

SpecOrch organizes software delivery into seven distinct planes:

### Contract Plane
*"What are we delivering?"*

Manages specs, scope, acceptance criteria, decisions, constraints, and unresolved questions. The spec is frozen here and becomes the single source of truth.

### Task Plane
*"How should we decompose the work?"*

Expands specs into executable task graphs with dependencies, ownership, blockers, state transitions, and work packets. Supports wave-based parallel execution.

### Harness Plane
*"How do we make execution reliable, not lucky?"*

Manages context contracts, skills, policies, setup hooks, runtime rules, reactions, fallback strategies, and cache-safe prompt layouts. This is the main battlefield for system improvement.

### Execution Plane
*"Who does the work, where, and with what isolation?"*

Manages worktrees, sandboxes, sessions, branches, runtime providers, and agent adapters. One task, one isolated workspace — always.

### Evidence Plane
*"Why should we believe this delivery is correct?"*

Manages findings, tests, preview links, diffs, deviations, review summaries, risk signals, and gate evidence. Completion is proven, not claimed.

### Control Plane
*"How does one person operate a fleet of tasks and agents?"*

Manages missions, task graphs, sessions, PR lifecycle, gate state, incidents, costs, stuck runs, and notifications. The operational command center.

### Evolution Plane
*"How does the system get better over time?"*

Manages run traces, retrospectives, prompt evolution, policy distillation, harness evals, and system-level tuning. Every run feeds back into the next.

---

## What SpecOrch Is NOT

- **Not a chat toy.** It is a delivery system with structured contracts and evidence.
- **Not a multi-agent social experiment.** It defaults to orchestrator-worker, not peer negotiation.
- **Not an IDE replacement.** It has a dashboard and TUI, but its identity is the control plane, not the editor.
- **Not a PR bot.** It does not just convert issues into PRs. It manages the full lifecycle from spec to evidence to evolution.

We do not pursue superficial agent autonomy. We pursue **delivery integrity**.

---

## Design Principles

| Principle | Meaning |
|-----------|---------|
| **Spec-first** | All execution starts from a frozen spec, not from vague intent |
| **Orchestration-first** | Default to clear central control, not emergent coordination |
| **Harness-first** | Solidify execution rails before optimizing model behavior |
| **Evidence-first** | No evidence, no completion |
| **Human-governed, machine-executed** | Humans own goals, boundaries, judgment, approval. Machines own decomposition, execution, verification, reporting |
| **Deterministic skeleton, adaptive intelligence** | The skeleton must be stable. Intelligence can evolve. Evolution must not break the skeleton |
| **Agent-First decisions** | When a decision requires project context, let an LLM decide and materialize the result as config — not as hardcoded rules |
| **Progressive operationalization** | Start as a Skill. Distill into a Policy. Harden into a Script/Gate/Hook. Move from experience to mechanism, not forever staying at the prompt layer |

---

## Our North Star

**Talk freely at the top.**
**Execute strictly in the middle.**
**Prove with evidence at the bottom.**
**Evolve the harness over time.**

This is not a feature slogan.
This is the system philosophy of SpecOrch.

---

## Current Realization

Today this philosophy is also reflected in explicit code seams:

- `runtime_core` for shared execution semantics and normalized read/write
- `decision_core` for supervision, decision recording, review, and intervention
- `acceptance_core` for routing, judgment, disposition, and calibration
- `acceptance_runtime` for bounded graph-based acceptance execution
- `contract_core` for contract, snapshot, and import semantics

`Issue` and `mission` ownership still stay separate where that boundary is
real, but both paths now speak the same execution and decision language.

---

## In One Sentence

**SpecOrch is the control plane for spec-driven software delivery.**
