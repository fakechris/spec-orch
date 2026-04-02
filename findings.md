# Findings & Decisions

## Requirements
- Keep iterating toward a runnable SpecOrch MVP on top of the already-merged prototype.
- Preserve project-local isolation with `.worktrees/` and `.venv`.
- Keep the next increment small enough to dogfood immediately.

## Research Findings
- `main` already contains the merged builder adapter and builder report artifacts.
- The current prototype still ends with `mergeable=False` by design because `human_acceptance` remains false.
- Closing the loop now requires an explicit acceptance mechanism more than another executor-side feature.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Prioritize a minimal human acceptance flow next | It is the last hard blocker to an end-to-end local mergeable path |
| Keep acceptance local-artifact based for now | This avoids premature Linear/PR integration while preserving a stable interface for later sync |
| Continue with isolated worktree implementation | This keeps `main` clean and matches the repo's operating model |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| None yet for this increment | - |

## Resources
- Current repository state on `main`
- Planning templates: `/Users/chris/.codex/skills/planning-with-files/templates/`
- Skills used: `superpowers:using-superpowers`, `superpowers:brainstorming`, `superpowers:test-driven-development`, `superpowers:using-git-worktrees`, `planning-with-files`

## Visual/Browser Findings
- No browser or image-based findings were needed for this increment.

## Session: 2026-03-25 Paperclip / Agent Observability Research

### Research Focus
- Paperclip as a reference point for strong agent observability and operator UX
- `agentcompanies.io` as a presentation layer for agent-company concepts
- `AgentCompany` and `agency-agents` as open-source implementations of multi-agent orchestration patterns
- Translation of those patterns into SpecOrch's supervised mission / round-loop model

### Working Hypotheses
- Paperclip likely wins on "operator visibility" through stronger live state surfaces, traceability, and run navigation.
- SpecOrch already has solid backend artifacts and auditability, but lacks a cohesive operator console that turns those artifacts into a first-class UX.
- The delta is probably not raw orchestration capability; it is presentation, drill-down ergonomics, and intervention flow.

### Source Findings
- Paperclip presents itself as "open-source orchestration for zero-human companies" and explicitly centers the operator dashboard around heartbeats, budgets, approvals, org charts, tickets, and full tracing rather than chat-first interaction.
- Paperclip's repository structure shows the model is deeply encoded in product surfaces, not just README copy: separate API/UI support exists for approvals, budgets, costs, heartbeats, issues, live runs, run transcripts, agents, projects, company settings, company import/export, and org charts.
- Paperclip's strongest observability move is object modeling. Instead of a generic log console, it gives named entities and pages for operator questions: costs, approvals, issue detail, run transcript, active agents, org chart, company portability.
- AgentCompany is explicitly inspired by Paperclip but is a local-first Electron desktop app. Its observable surfaces skew toward dashboard + communication + org chart + task queue + approval inspector. It appears more polished as a single-user desktop control plane, but lighter on deep audit primitives than Paperclip.
- AgentCompany's architecture is local-first and desktop-centered: Electron main process handles orchestration/database/services, React renderer handles the control plane, and runtime adapters live in local packages for Claude/Codex/Gemini.
- agentcompanies.io is not an operator console. It is a vendor-neutral package/specification layer describing how companies/teams/agents/projects/tasks/skills compose in markdown. The key value is portability and progressive disclosure, not runtime observability.
- `agency-agents` is also not an operator console. It is a large role/agent library with strong specialization and deliverable orientation, useful as role content or company templates, but not a visibility/control-plane reference.

### Emerging Comparison
- Paperclip = strongest reference for auditability, control plane vocabulary, and "operator can answer what is happening right now and why" UX.
- AgentCompany = strongest reference for approachable local UX, onboarding, and desktop-style live interaction surfaces.
- agentcompanies.io = strongest reference for portable package model and content structure that could underlie company templates.
- agency-agents = strongest reference for reusable role/skill payloads, not runtime observability.

### Paperclip-Specific Observability Takeaways
- Paperclip treats the human as a "board operator" and documents their workflow explicitly. Costs, budgets, approvals, and org structure all have separate operator guides and matching UI/API surfaces.
- Paperclip's cost model is not just a ledger dump. It exposes company budget, per-agent budget, alert thresholds, auto-pause behavior, and breakdown views by agent/project/provider. This turns "what did we spend?" into an explorable control surface.
- Paperclip's approval model is similarly first-class: there is an approval queue, typed approval payloads, linked issues, revision flows, and explicit board override powers.
- The run transcript UI is highly intentional. It distinguishes assistant/user messages, thinking, tools, activities, command groups, stdout, and generic events. This is a much richer runtime narrative than a plain JSONL viewer.

### Implication For SpecOrch
- SpecOrch already stores enough artifacts to support many of these answers, but it does not yet express them as product objects. Today the operator mentally assembles the answer from files; Paperclip shows the answer as a page.

### Implementation Decision
- Do not rewrite the dashboard stack immediately.
- Keep FastAPI as the dashboard backend and incrementally refactor `src/spec_orch/dashboard.py` into a modular dashboard package with static assets and dedicated mission/transcript APIs.
- This keeps the current product runnable while still allowing the operator console to evolve into a workbench-style UI.

### Execution Findings
- A full Python package/module split under the same name as `src/spec_orch/dashboard.py` would conflict with Python import resolution. The implementation should therefore proceed incrementally, starting with external static assets and new API projections, then move into a larger module split later.
- The lowest-risk first code slice is backend-first:
  - keep the existing dashboard route structure alive
  - add `/static` entrypoints
  - add mission detail and transcript projections
  - only then rebuild the UI shell on top

## Session: 2026-03-27 yoyo-evolve Harness Research

### Research Focus
- Deeply inspect `yologdev/yoyo-evolve` as a harness engineering case study.
- Compare its self-evolution loop, memory system, personality/identity model, and social vision against SpecOrch.
- Identify what is directly borrowable versus what belongs to a different product thesis.

### Source Findings
- `yoyo-evolve` treats `IDENTITY.md`, `PERSONALITY.md`, `JOURNAL.md`, `memory/active_learnings.md`, and `memory/active_social_learnings.md` as operational prompt assets, not passive documentation.
- The evolution loop is tightly bounded: one evolution cycle, explicit plan/implement/respond phases, mandatory `cargo build`/`cargo test`, revert-on-failure, and a public journal entry every session.
- The project’s “wildness” is constrained less by product management and more by a strong constitution plus a very narrow self-edit loop. It grows autonomously, but within a heavily ritualized engineering envelope.
- Memory is explicitly layered:
  - append-only JSONL archives as source of truth
  - daily-synthesized active markdown for prompt injection
  - separate self-learnings and social-learnings
  - context assembly through `scripts/yoyo_context.sh`
- Social behavior is part of the architecture, not a side project:
  - `social.sh` runs periodic discussion sessions
  - `create_address_book.sh` and the `yoyobook` category define a fork-family registry
  - sponsor economics and social learnings feed operational behavior
- `yoyo`'s personality is intentionally lightweight but persistent: “small octopus growing up in public,” curious/honest/stubborn, and this persona is reinforced by both docs and prompt context.

### Comparison Implications For SpecOrch
- SpecOrch is stronger as a delivery control plane: explicit missions, rounds, approvals, acceptance artifacts, budget/QA/operator surfaces.
- `yoyo-evolve` is stronger as an agent-selfhood system: identity continuity, memory continuity, autobiographical evolution, and socially legible personality.
- SpecOrch’s current memory architecture is infrastructurally richer but less narratively alive; it stores task and run knowledge, but not a durable “who am I becoming?” layer.
- SpecOrch’s operator console and mission launcher already surpass `yoyo` on multi-surface observability, but `yoyo` is ahead on making evolution itself inspectable as a story.

### Roadmap Alignment Decision
- Keep `SON-74` as the completed self-evolution baseline. Do not reopen it to absorb new harness-engineering work.
- Normalize `SON-234` into a real epic and attach `SON-235..241` as its child issues so operator-console depth work has an actual parent epic.
- Create a dedicated adversarial/exploratory acceptance epic instead of hiding it under operator-console tasks:
  - `SON-242` with children `SON-245..248`
- Create a dedicated selfhood/memory-synthesis epic for the yoyo-inspired borrowings:
  - `SON-243` with children `SON-249..252`
- Create a bounded operator-feedback/social-learning epic instead of overcommitting to a full social-product pivot:
- `SON-244` with children `SON-253..256`

## Session: 2026-04-01 Operator Workbench Program

### Fresh-branch baseline
- Created a clean worktree from latest `origin/main` at:
  `/Users/chris/workspace/spec-orch/.worktrees/operator-workbench-program`
- Avoided mutating the dirty local `main` worktree, which is ahead/behind and
  contains unrelated untracked files.

### Existing architecture baseline
- Current `main` already contains the `llm_planner_orch` merge (`origin/main`
  at `21aeb4a`).
- Existing planning corpus already covers:
  - 7-epic architecture extraction
  - Epic 4 acceptance judgment and calibration
  - runtime package best practices
  - dashboard/operator-console slices

### Rebase insight
- The next planning wave should not replace the current extraction program.
- It should reframe the product-facing outcome around three visible operator
  workbenches:
  - Execution
  - Judgment
  - Learning
- The correct architectural relationship is:
  - `runtime_core` / runtime packages supply execution truth
  - `decision_core` / `acceptance_core` supply judgment truth
  - memory/evolution supply learning truth
  - workbenches become the operator-visible control plane over those seams

### Linear creation feasibility
- `LINEAR_TOKEN` is available in environment.
- Team query succeeded.
- Team confirmed:
  - key: `SON`
  - name: `Songwork`
- Existing epic pattern in Linear uses parent issue titles like:
  - `[Epic] Runtime Chain Observability and Live Traceability`
- Existing epic/sub-issue relationship is standard Linear parent/children, so
  parent issues and child issues can be created directly from this session.

### Linear creation result
- Created a new 7-epic / 30-issue operator-workbench program directly in Linear.
- ID ranges:
  - epics: `SON-370`, `SON-374`, `SON-379`, `SON-384`, `SON-390`, `SON-396`, `SON-402`
  - children: `SON-371..373`, `SON-375..378`, `SON-380..383`, `SON-385..389`,
    `SON-391..395`, `SON-397..401`, `SON-403..406`
- The local source of truth for exact mapping is:
  - `docs/plans/2026-04-01-operator-workbench-linear-plan.md`
