# SON-264 Runtime Responsibility Split

> `SON-264` = Exploratory campaign planner and bounded route expansion.
>
> This document defines who owns what at runtime, which layers are deterministic,
> which layers require LLM reasoning, and how `Exploratory Acceptance` differs
> from `Workflow Replay E2E`.

## Goal

Make `Exploratory Acceptance` reproducible enough to run inside the harness while
still using model reasoning where user-perspective judgment is actually needed.

The target is not "let the model freely browse the app."

The target is:

1. The harness owns execution and safety.
2. The model owns bounded exploratory reasoning.
3. Findings stay structured and reviewable.

## Core Split

Runtime responsibility is split across four layers:

1. Campaign Compiler
2. Harness Runtime
3. Exploration Advisor
4. Critique Evaluator

The first two should be mostly deterministic.
The last two require LLM reasoning.

## 1. Campaign Compiler

### Responsibility

Compile a concrete exploratory campaign from a higher-level acceptance scope.

This layer decides:

- which surface is in scope
- which seed routes to start from
- which expansion rules are allowed
- what the route / interaction / evidence budgets are
- what stop conditions apply
- what critique dimensions matter for this run

### Inputs

- acceptance range / mission scope
- product surface metadata
- acceptance mode = `exploratory`
- optional explicit user focus
  - e.g. dashboard IA, mission discoverability, approval UX

### Outputs

A structured exploratory campaign payload, for example:

- `surface_scope`
- `seed_routes`
- `allowed_expansions`
- `route_budget`
- `interaction_budget`
- `stop_policy`
- `critique_focus`
- `filing_policy`

### LLM Requirement

Optional.

This layer can start rule-based and template-driven.
Later it may use LLM assistance to suggest better seeds or focus areas, but that
is not required for the first implementation.

### Owner

Harness-owned.

This is a runtime planning layer, not a freeform model task.

## 2. Harness Runtime

### Responsibility

Execute the exploratory campaign under strict deterministic control.

This layer owns:

- browser execution
- route visit tracking
- expansion budget tracking
- allowed action filtering
- stop condition enforcement
- evidence capture
- artifact persistence

### Inputs

- compiled exploratory campaign
- base URL / target app
- browser runner
- route/action state

### Outputs

- `browser_evidence.json`
- screenshots / visual captures
- interaction log
- tested route set
- explored edge set
- expansion summary

### LLM Requirement

No.

This should be deterministic and owned by code. The harness may ask an LLM for
"which candidate next step is most promising", but the harness decides:

- what candidate set exists
- whether the suggestion is allowed
- whether budget remains
- whether execution continues

### Owner

Harness-owned.

This is the runtime authority.

## 3. Exploration Advisor

### Responsibility

Choose the next most valuable exploratory branch from a bounded set of
candidates.

This layer answers questions like:

- which visible branch is most likely to reveal discoverability problems?
- should we inspect a nearby tab, detail surface, or contextual link next?
- which route is more likely to expose IA or terminology confusion?

### Inputs

- current route
- currently visible UI affordances
- candidate next actions/routes from harness
- critique focus
- remaining budget
- partial evidence so far

### Outputs

- ranked candidate next steps
- rationale for ranking
- optional suspicion tags
  - `ia_confusion`
  - `terminology_ambiguity`
  - `discoverability_risk`
  - `context_switching_friction`

### LLM Requirement

Yes.

This is where bounded semantic reasoning is valuable. It should not emit raw
browser commands. It should only rank or annotate harness-provided candidates.

### Owner

LLM node inside the harness.

Not the top-level orchestrator.

## 4. Critique Evaluator

### Responsibility

Interpret collected exploratory evidence into structured findings.

This layer decides:

- what is likely a UX / IA / discoverability problem
- what is likely just noise
- what should be held for human review
- what is serious enough to escalate

### Inputs

- browser evidence
- screenshots
- tested routes
- interaction log
- critique focus
- filing / hold policy

### Outputs

Structured exploratory findings, for example:

- `summary`
- `route`
- `evidence_refs`
- `category`
- `confidence`
- `hold_reason`
- `recommended_next_step`

### LLM Requirement

Yes.

This is where user-perspective judgment lives.

### Owner

LLM evaluator inside the acceptance stack.

## Deterministic vs LLM Responsibilities

### Deterministic / hard-coded

These should be implemented as code, not delegated to prompt freestyle:

- accepted campaign schema
- expansion budget accounting
- stop conditions
- allowed action families
- allowed expansion edges
- evidence capture format
- hold / file policy enforcement
- artifact layout
- replay reproducibility guarantees

### LLM / reasoning-driven

These should use model reasoning:

- candidate branch prioritization
- user-perspective critique
- IA / terminology / discoverability judgments
- structured exploratory finding drafting

## Why This Is Different From Workflow Acceptance

`Workflow Acceptance` uses a fixed-flow schema.

Its structure is:

- predefined routes
- predefined interactions
- predefined assertions
- goal = prove the flow works

`Exploratory Acceptance` uses a bounded-exploration schema.

Its structure is:

- predefined boundary
- predefined seeds
- predefined budgets
- predefined allowed expansions
- model-assisted next-step choice
- goal = find confusing, hard-to-discover, or awkward user experiences

So the difference is not "schema vs no schema."

The difference is:

- `Workflow` = route script schema
- `Exploratory` = bounded exploration schema

## Relationship to Prompt and Skill

### Skill

The skill defines the execution protocol:

- how to run exploratory acceptance
- required inputs
- required outputs
- runtime guardrails
- debugging workflow

The skill should be generic.

### Prompt

The prompt defines the judgment protocol:

- what counts as IA confusion
- what counts as terminology ambiguity
- what counts as discoverability friction
- when to hold vs escalate

The prompt should be generic skeleton + campaign-specific focus injection.

### Campaign

The campaign is the run-specific instance:

- which routes
- which surface
- which budget
- which critique focus

The campaign should vary by acceptance range.

## Generic vs Range-Specific Pieces

### Generic

- exploratory acceptance skill
- exploratory campaign schema
- harness runtime
- evidence schema
- evaluator output schema
- critique rubric skeleton

### Range-specific

- seed routes
- allowed expansions
- critique focus priorities
- stop policy tuning
- hold / escalation thresholds

So we should not generate a brand-new skill for each acceptance scope.

We should:

1. keep one generic exploratory skill
2. keep one generic exploratory schema
3. generate a different campaign instance per scope

## First Implementation Guidance for SON-264

The first implementation should keep the split conservative:

1. Campaign Compiler: deterministic
2. Harness Runtime: deterministic
3. Exploration Advisor: LLM-ranked candidates only
4. Critique Evaluator: LLM-generated structured findings

Do not start with:

- freeform browsing
- model-generated raw commands
- model-owned stopping logic
- auto-filing exploratory critique

## Practical Rule

If a decision affects safety, repeatability, or scope:

- harness owns it

If a decision depends on user-perspective semantics:

- LLM may advise or evaluate it

That is the runtime split `SON-264` should implement.
