# Skill-Driven vs Spec-Driven Orchestration

> Discussion originated during Conductor Agent development (PR #39, Epic SON-83).
> Linear issues: SON-97 (architecture exploration), SON-98 (intent-aware DMA).

## The Problem

spec-orch uses a **Spec-Driven** model: a hard-coded Python pipeline
(Approve → Plan → Promote → Execute → Retro → Evolve) drives the entire
lifecycle. When the process needs to change, the code itself must change,
followed by tests, review, and deployment.

This stands in contrast to **Skill-Driven** models (e.g. Claude Code Skills,
Codex hooks, Cursor rules) where:

- Pipeline steps are described in natural language as Skills
- An LLM-based orchestrator selects which Skills to invoke at runtime
- Changing behavior means editing a Skill definition, not re-coding a pipeline
- New capabilities compose through Skill combination rather than code wiring

## Observed Failure Mode

During the Conductor Agent implementation, the development agent (DMA) skipped
the Linear issue creation step and went straight to writing code. This happened
because:

1. The DMA's "process knowledge" is encoded in conversation context and prior
   instructions, not enforced by the pipeline itself.
2. No gate or check prevented starting code before an Issue existed.
3. The user raised new concerns mid-review (Skill-Driven architecture, intent
   routing) — the system had no mechanism to fork these into separate work
   items while continuing the review.

This is the exact scenario the Conductor Agent is designed to handle, but the
Conductor was the thing being built — a chicken-and-egg problem that highlights
why the orchestration layer itself needs to be more flexible.

## Comparison Matrix

| Dimension             | Spec-Driven (current)           | Skill-Driven (proposed)          |
|-----------------------|---------------------------------|----------------------------------|
| Process definition    | Python code + state machines    | Natural language + Skill files   |
| Change velocity       | Code PR → CI → Deploy           | Edit Skill text → immediate      |
| Correctness guarantees| Type-checked, tested pipeline   | LLM-dependent, probabilistic    |
| Composability         | Explicit wiring in code         | LLM selects from Skill registry |
| Debuggability         | Stack traces, deterministic     | LLM reasoning traces, stochastic|
| Drift handling        | Not supported (rigid gates)     | Intent classification per turn  |

## Proposed Hybrid Architecture

Neither pure Spec-Driven nor pure Skill-Driven is ideal. A hybrid approach:

```
User Message
    │
    ▼
┌──────────────────┐
│  Conductor Agent │  ← Skill-Driven: LLM classifies intent, routes
│  (Skill layer)   │     and forks work items dynamically
└────────┬─────────┘
         │
    ┌────▼────┐
    │ Router  │  ← Decides: quick response, new issue, or pipeline entry
    └────┬────┘
         │
    ┌────▼──────────────┐
    │ Lifecycle Pipeline │  ← Spec-Driven: deterministic execution
    │ (Plan → Execute)   │     with quality gates and evidence
    └───────────────────┘
```

- **Top layer (Skill-Driven):** Intent classification, conversation routing,
  work item creation, drift detection. Described as Skills so behavior can be
  tuned without code changes.
- **Bottom layer (Spec-Driven):** The actual engineering lifecycle
  (planning, code generation, testing, review, retrospective). Keeps its
  deterministic guarantees for execution quality.
- **Bridge (Conductor):** Progressive formalization converts conversations
  into structured inputs for the pipeline.

## Key Design Principle

> "Talk freely, execute strictly."

The conversational layer should be as flexible as chatting with a colleague.
The execution layer should be as rigorous as a CI/CD pipeline. The Conductor
is the bridge that converts one into the other.

## Implementation Considerations

1. **Skill Registry:** Define core pipeline steps as Skills that the Conductor
   can invoke. Start with the existing stages as Skill descriptions.
2. **Gate Enforcement via Skills:** Instead of hard-coding "must have Linear
   issue before coding," encode this as a pre-execution Skill check.
3. **Parallel Intent Routing:** When a user raises multiple concerns in one
   message, the Conductor should be able to fork — handle the primary flow
   while creating separate work items for secondary concerns.
4. **Graceful Degradation:** If the LLM-based routing fails, fall back to
   the deterministic pipeline (current behavior).

## Related Work

- "Talk Freely, Execute Strictly" (arxiv 2603.06394)
- Microsoft RiSE Intent Formalization
- Claude Code Skill/Hook/Cron model
- Schema-Gated Orchestration pattern
