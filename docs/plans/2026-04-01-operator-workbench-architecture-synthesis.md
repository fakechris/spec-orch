# Operator Workbench Architecture Synthesis

> **Date:** 2026-04-01
> **Status:** pre-implementation architecture lock
> **Purpose:** converge the operator-facing product and the underlying runtime
> architecture before starting the next implementation wave

## 1. Executive Summary

SpecOrch should not evolve into a generic AI IDE, a generic task board, or a
chat-first agent shell.

It should become an **operator-grade agent workbench** with three linked
surfaces:

1. `Execution Workbench`
2. `Judgment Workbench`
3. `Learning Workbench`

These surfaces must sit on top of two code-owned substrates:

1. `runtime and execution substrate`
2. `decision and judgment substrate`

And both substrates must speak one shared vocabulary:

1. `shared operator semantics`

This leads to a stable six-layer model:

1. shared operator semantics
2. runtime and execution substrate
3. decision and judgment substrate
4. execution workbench
5. judgment workbench
6. learning workbench

The core design rule is:

**execution truth must be runtime-owned, judgment truth must be
decision-owned, and dashboard surfaces must only consume canonical seams.**

This is the only path that gives SpecOrch:

- Intent-level execution productization
- Multica-level runtime and agent visibility
- SpecOrch-native acceptance, calibration, memory, and evolution

## 2. The Product We Are Actually Building

The product is not:

- a prettier mission detail page
- a set of acceptance JSON viewers
- a lightweight clone of Linear
- a general-purpose AI IDE

The product is:

**a workspace-protocol-driven operator workbench for supervised agent delivery**

This means an operator must be able to answer, from the UI alone:

### Execution questions

- What is running now?
- Which agent owns it?
- Which runtime is it on?
- What phase is it in?
- Is it healthy, stalled, degraded, or blocked?
- What can I do right now?

### Judgment questions

- What did the system evaluate?
- What evidence did it use?
- Why is the current judgment pass, warn, or fail?
- Which concerns are confirmed?
- Which concerns are only candidate findings?
- What evidence is missing to promote or dismiss them?

### Learning questions

- What patterns are recurring?
- Which findings became fixtures?
- Which reviewed findings flowed into memory?
- Which evolution or policy changes came from reviewed evidence?
- What was promoted, rolled back, or retired?

If the UI cannot answer those questions clearly, the system is still too
backend-shaped.

## 3. Structural Principles

### 3.1 Runtime owns execution truth

Execution truth includes:

- task ownership
- active work
- queue state
- runtime identity
- health and heartbeat
- progress summaries
- event trails
- intervention records
- browser and terminal runtime state

The dashboard may render this truth and trigger actions against it, but it must
not invent its own execution state machine.

### 3.2 Decision owns judgment truth

Judgment truth includes:

- acceptance routing
- base run mode
- graph profile
- compare overlay activation
- evidence plan
- judgment class
- review and disposition state
- candidate finding promotion rules

The dashboard may visualize judgment and drive human review, but it must not
decide what a confirmed issue or candidate finding means.

### 3.3 Learning only promotes reviewed outcomes

No raw run artifact should become long-term product truth directly.

Promotion into:

- fixture
- memory
- evolution proposal
- policy change

must happen only from reviewed judgment outputs.

### 3.4 Workspace protocol is a first-class concept

The operator does not interact with isolated pages.
The operator interacts with a workspace that binds:

- issue or mission
- spec
- task graph
- active execution
- evidence
- judgment
- learning lineage

The workspace protocol is not a separate epic, but it must be explicitly owned
across Epics 1, 2, and 4.

## 4. Target Layer Model

## 4.1 Shared Operator Semantics

This layer defines the common vocabulary for all operator-facing surfaces.

Canonical objects:

- `Workspace`
- `Run`
- `ExecutionSession`
- `Agent`
- `Runtime`
- `Task`
- `EventEnvelope`
- `ArtifactEnvelope`
- `Intervention`
- `EvidenceBundle`
- `Judgment`
- `ConfirmedIssue`
- `CandidateFinding`
- `Observation`
- `PromotedFinding`
- `Fixture`
- `MemoryEntryRef`
- `EvolutionProposalRef`

Without this layer, execution, judgment, and learning pages will drift into
different naming systems.

## 4.2 Runtime and Execution Substrate

This layer owns:

- runtime registry
- active work and queue carriers
- event and progress streams
- intervention hooks
- browser and terminal runtime surfaces
- tool runtime
- workspace-local bridge seams

This is where the system absorbs the strongest execution patterns from mature
agent workbenches.

## 4.3 Decision and Judgment Substrate

This layer owns:

- routing inputs
- mode selection
- compare overlay activation
- evidence provenance
- judgment classes
- disposition state carriers
- calibration drift carriers

This is where `acceptance_core` and `decision_core` should stabilize the meaning
of:

- `verify`
- `replay`
- `explore`
- `recon`
- `confirmed_issue`
- `candidate_finding`
- `observation`

## 4.4 Execution Workbench

This is the operator control plane for live work.

It must expose at least:

- `Agents`
- `Runtimes`
- `Active Work`
- `Queue`
- `Execution Session`
- `Interventions`
- `Browser / terminal / changes side surfaces`

## 4.5 Judgment Workbench

This is the operator review plane for evidence and acceptance.

It must expose at least:

- `Evidence Bundle`
- `Judgment Timeline`
- `Candidate Findings`
- `Compare Overlay`
- `Surface Pack Inspector`

## 4.6 Learning Workbench

This is the operator plane for seeing how the system changes over time.

It must expose at least:

- `Learning Timeline`
- `Pattern Registry`
- `Fixture Registry`
- `Memory-linked Findings`
- `Evolution Proposal Review`
- `Promotion / Rollback History`

## 5. Current Codebase → Target Convergence Map

The current codebase already contains many of the right capabilities, but they
are still spread across `services/` and `dashboard/` rather than cleanly owned
by substrate vs workbench layers.

## 5.1 Current execution-related code

Relevant files today:

- `src/spec_orch/services/run_controller.py`
- `src/spec_orch/services/parallel_run_controller.py`
- `src/spec_orch/services/mission_execution_service.py`
- `src/spec_orch/services/mission_service.py`
- `src/spec_orch/services/daemon.py`
- `src/spec_orch/services/run_artifact_service.py`
- `src/spec_orch/services/artifact_service.py`
- `src/spec_orch/services/workers/in_memory_worker_handle_factory.py`

These files should converge into the **runtime and execution substrate**.

They should become the canonical owners of:

- run ownership
- task/session progression
- active work inventory
- runtime health
- event trail
- intervention hooks
- workspace execution context

### Immediate direction

- Keep these modules operational where they are for now.
- Treat them as the raw source for Epic 2 carriers.
- Do not let dashboard modules grow private execution truth on top of them.

## 5.2 Current judgment-related code

Relevant files today:

- `src/spec_orch/services/round_orchestrator.py`
- `src/spec_orch/services/acceptance/browser_evidence.py`
- `src/spec_orch/services/acceptance/prompt_composer.py`
- `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- `src/spec_orch/services/acceptance/linear_filing.py`
- `src/spec_orch/services/review_adapter.py`
- `src/spec_orch/services/llm_review_adapter.py`
- `src/spec_orch/services/github_review_adapter.py`

These files should converge into the **decision and judgment substrate**.

They should become the canonical owners of:

- acceptance routing
- evidence bundle production
- evaluation scope
- judgment class assignment
- review state and disposition
- filing thresholds

### Immediate direction

- Keep evaluator semantics out of dashboard page code.
- Continue moving mode selection and judgment semantics into canonical contracts.
- Make `round_orchestrator` a consumer of decision rules, not a permanent home
  for judgment ontology.

## 5.3 Current learning-related code

Relevant files today:

- `src/spec_orch/services/memory/service.py`
- `src/spec_orch/services/memory/analytics.py`
- `src/spec_orch/services/memory/distiller.py`
- `src/spec_orch/services/memory/derivation.py`
- `src/spec_orch/services/memory/recorder.py`
- `src/spec_orch/services/evolution/evolution_trigger.py`
- `src/spec_orch/services/evolution/prompt_evolver.py`
- `src/spec_orch/services/evolution/intent_evolver.py`
- `src/spec_orch/services/evolution/skill_evolver.py`
- `src/spec_orch/services/evolution/flow_policy_evolver.py`
- `src/spec_orch/services/evolution/gate_policy_evolver.py`

These files should converge into the **learning substrate** consumed by the
Learning Workbench.

They should own:

- memory ingestion
- memory analytics
- reviewed finding linkage
- evolution proposal generation
- policy promotion lineage

### Immediate direction

- Do not mix raw memory internals into dashboard code.
- Expose reviewed and promoted learning artifacts as canonical read models.
- Keep promotion and rollback auditable.

## 5.4 Current dashboard code

Relevant files today:

- `src/spec_orch/dashboard/app.py`
- `src/spec_orch/dashboard/api.py`
- `src/spec_orch/dashboard/routes.py`
- `src/spec_orch/dashboard/shell.py`
- `src/spec_orch/dashboard/control.py`
- `src/spec_orch/dashboard/missions.py`
- `src/spec_orch/dashboard/transcript.py`
- `src/spec_orch/dashboard/approvals.py`
- `src/spec_orch/dashboard/surfaces.py`
- `src/spec_orch/dashboard/launcher.py`
- `src/spec_orch/dashboard_assets/static/operator-console.js`
- `src/spec_orch/dashboard_assets/static/operator-console.css`

These files should converge into the **workbench layer** only.

They should not remain a mixed zone that:

- queries data
- defines domain semantics
- encodes review state
- invents page-local models

### Immediate direction

- `dashboard/api.py` should increasingly become a workbench composition entry,
  not a loose re-export file.
- `dashboard/app.py` should keep shrinking into shell/bootstrap responsibilities.
- `dashboard/*` modules should gradually split by workbench responsibility:
  - execution
  - judgment
  - learning

## 6. Recommended Future Package Ownership

This is a **target ownership model**, not a mandatory immediate folder move.

### Shared operator semantics

Likely home:

- `src/spec_orch/domain/`

Examples:

- operator ids
- state enums
- artifact carriers
- event envelopes
- intervention records

### Runtime and execution substrate

Likely home:

- future `src/spec_orch/runtime_core/`
- or a staged subset extracted from `src/spec_orch/services/`

Examples:

- run controller seam
- runtime registry
- active work carrier
- queue carrier
- progress and event streams
- local bridge contracts
- browser/runtime panel substrate

### Decision and judgment substrate

Likely home:

- future `src/spec_orch/decision_core/`
- plus `src/spec_orch/services/acceptance/` during transition

Examples:

- acceptance routing
- evidence bundle provenance
- compare overlay carriers
- judgment/disposition carriers
- candidate finding carriers

### Workbench surfaces

Likely home:

- `src/spec_orch/dashboard/`

Examples:

- execution workbench pages and API handlers
- judgment workbench pages and API handlers
- learning workbench pages and API handlers

The dashboard should become a **consumer shell** over stable seams, not a place
where substrate rules are authored.

## 7. What Users Must See In The UI

This is the most important external requirement.

The operator must be able to understand what the system is doing without reading
backend logs or raw JSON.

## 7.1 Execution Workbench: user-visible contract

The UI must make these visible:

- current owner agent
- current runtime
- current phase
- health and heartbeat
- queue state
- recent events
- available interventions
- current browser or terminal activity when relevant

### The operator should be able to read it as:

- `Verifier running on runtime-3`
- `Waiting on browser replay`
- `Retry available`
- `Stalled for 7m on verification`
- `Last action: browser capture failed with auth redirect`

This is where Intent and Multica are ahead today.

## 7.2 Judgment Workbench: user-visible contract

The UI must make these visible:

- what was evaluated
- what evidence was collected
- current run mode
- current judgment class
- confidence
- impact if true
- repro status
- next promotion test
- rationale for the current disposition

### The operator should be able to read it as:

- `Explore mode on transcript surface`
- `Candidate finding: transcript empty state hides retry cause`
- `Confidence: medium`
- `Impact if true: high`
- `Promotion test: rerun transcript path with retry cause visible`

This is where SpecOrch must stay differentiated.

## 7.3 Learning Workbench: user-visible contract

The UI must make these visible:

- repeated patterns
- promoted findings
- fixture candidates
- memory linkage
- evolution proposals
- policy promotions and rollbacks

### The operator should be able to read it as:

- `This issue pattern has appeared in 5 runs`
- `Promoted to dashboard empty-state fixture`
- `Linked to memory: operator evidence discoverability`
- `Flow policy proposal created from reviewed findings`

Without this, learning stays backend-only and the system feels opaque.

## 8. What To Borrow Directly From Intent and Multica

These should be treated as **must-adopt structural patterns**, not as optional
inspiration.

### From Intent

- workspace protocol as a first-class product concept
- local bridge between UI and runtime
- browser panel as a first-class workspace surface
- specialist roles as product objects, not only service names
- spec/task/note/agent collaboration discipline
- stronger stateful execution visibility instead of chat-first interaction

### From Multica

- agent roster as a first-class surface
- runtime roster as a first-class surface
- issue execution as a first-class operator workflow
- queue and live task visibility
- runtime usage and activity visibility

### What should not be copied directly

- a generic PM-system frame that weakens supervised delivery semantics
- a chat-first UX that hides execution state
- a purely execution-centric model that has no judgment or learning layer

## 9. Spec and Contract Split For The Next Planning Wave

Before implementation proceeds deeply, the next planning set should explicitly
exist as six documents:

1. `Execution Workbench Spec`
2. `Execution Workbench Contract`
3. `Judgment Workbench Spec`
4. `Judgment Workbench Contract`
5. `Learning Workbench Spec`
6. `Learning Workbench Contract`

And one shared cross-cutting document:

7. `Workspace Protocol Spec`

## 10. Execution Sequence

The correct order remains:

1. shared operator semantics
2. runtime and execution substrate
3. decision and judgment substrate
4. execution workbench
5. judgment workbench
6. learning workbench
7. cleanup and cutover

### Why this order is still correct

- without semantics, every surface invents its own truth
- without runtime substrate, execution workbench becomes UI theatre
- without judgment substrate, candidate finding and compare semantics leak into
  page code
- without execution and judgment surfaces, learning remains unreadable and
  unauditable

## 11. Immediate Planning Conclusions

### 11.1 Do not start by redesigning the whole dashboard

The next steps should not be:

- one huge UI rewrite
- more one-off pages
- a direct clone of Intent or Multica

### 11.2 Do start by locking the seams

The next steps should be:

- define the workspace protocol
- harden execution carriers
- harden judgment carriers
- define workbench-facing API contracts
- then build the workbench surfaces against those contracts

### 11.3 Treat user legibility as a hard requirement

Operator-facing clarity is not polish.

It is a product requirement:

- the user must understand what the backend is doing
- the user must understand why the system judged what it judged
- the user must understand what the system learned and changed

If any of those are only reconstructible from raw artifacts, the workbench is
still incomplete.

## 12. Final Position

SpecOrch should explicitly become:

**a workspace-protocol-driven operator workbench with execution, judgment, and
learning planes**

This allows the project to absorb the best structural lessons from mature
agent-native workbenches while preserving its own real advantage:

- supervised delivery
- evidence-driven judgment
- candidate finding review
- calibration and compare overlays
- memory and evolution promotion
