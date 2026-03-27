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
