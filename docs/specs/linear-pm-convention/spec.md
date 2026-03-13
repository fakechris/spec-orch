# Linear Project Management Convention

A specification for organizing Linear projects so that AI orchestrators (spec-orch daemon) and human developers share a single, unambiguous source of truth for task execution.

## 1. Three-Layer Object Model

Every Linear workspace managed by spec-orch uses exactly three layers of issues:

### Layer 1 — Project

A Project groups related epics and provides portfolio-level tracking.

- One Project per repository or product domain.
- Not directly consumable by agents.
- Provides progress aggregation across epics.

### Layer 2 — Parent Issue (Epic / Feature)

A parent issue defines a capability, theme, or feature scope.

- Labeled `epic` or `feature`.
- Contains: goal, scope boundary, acceptance criteria (aggregate), dependencies.
- **Never enters the agent execution queue.** Agents do not pick up parent issues.
- Progress is derived from child issue completion.

### Layer 3 — Executable Issue (Task)

The atomic unit of work for an agent or human developer.

- Labeled `task`, `bug`, `ops`, `spec`, or `review`.
- Must be a child of a parent issue (preferred) or standalone.
- Has a structured description (see Section 5).
- Only this layer is eligible for daemon consumption.

## 2. Workflow State Machine

Six states, linear progression:

```
Backlog → Ready → In Progress → In Review → Done
                                              ↘ Canceled
```

### State Semantics

| State | Type | Meaning | Agent action |
|-------|------|---------|-------------|
| Backlog | backlog | Idea pool, unrefined | Do not consume |
| Ready | unstarted | Requirements clear, context complete, eligible for execution | **Primary entry point** — daemon polls this state |
| In Progress | started | Agent or human actively working | Do not re-assign |
| In Review | started | Code/output submitted, awaiting review or gate | Review agent or human reviews |
| Done | completed | Fully closed — merged, verified, accepted | Terminal |
| Canceled | canceled | Will not be done | Terminal |

### Transition Rules

- **Backlog → Ready**: Human triage. Issue must meet completeness requirements (Section 5).
- **Ready → In Progress**: Daemon claims the issue. Moves state via API.
- **In Progress → In Review**: Build + PR completed. Daemon moves state.
- **In Review → Done**: Gate passes + merge. Daemon or GitHub integration moves state.
- **Any → Canceled**: Human decision only.

## 3. Label System

### Type Labels (mutually exclusive per issue)

| Label | Color | Usage |
|-------|-------|-------|
| `epic` | gray | Parent issues only |
| `feature` | purple (existing) | Alternative to `epic` for smaller features |
| `task` | blue | Standard executable work |
| `bug` | red (existing) | Defect fix |
| `spec` | purple | Specification or design work |
| `ops` | indigo | Infrastructure, deployment, config |

### Execution Qualification Labels

| Label | Color | Meaning |
|-------|-------|---------|
| `agent-ready` | green | Optional — explicitly marks an issue as agent-eligible (set automatically by PromotionService) |
| `blocked` | red | Issue is blocked, do not consume |
| `needs-clarification` | amber | Daemon posted questions, awaiting human reply |

### Rules

- An issue enters the agent queue when **all** conditions are met:
  1. `state == Ready`
  2. Does **not** have label `blocked`
  3. Does **not** have label `needs-clarification`
  4. Is **not** a parent issue (has no children)
- The `agent-ready` label is **not required** for consumption. Dragging an issue to Ready is sufficient user intent.
- The daemon runs a **readiness triage** on each candidate (see Section 4) before execution.

## 4. Daemon Consumption Protocol

### Configuration

```toml
[daemon]
consume_state = "Ready"
require_labels = []
exclude_labels = ["blocked", "needs-clarification"]
skip_parents = true
```

### Poll Logic

```text
0. Check needs-clarification issues for user replies:
   - If user replied → remove needs-clarification label → re-enter pool
1. Query Linear: state=Ready, labels exclude blocked and
   needs-clarification, no children
2. For each qualifying issue:
   a. Claim (lockfile)
   b. Readiness triage (see Section 4a)
      - If NOT ready → post clarification comment, add
        needs-clarification label, release lock, skip
   c. Move state → In Progress
   d. Execute build pipeline
   e. On success: create PR, move → In Review
   f. On gate pass + merge: move → Done
   g. On failure: leave In Progress, add comment with error
```

### 4a. Readiness Triage

Before executing, the daemon evaluates the issue description:

1. **Rule check**: Goal, Acceptance Criteria, Files in Scope must be present.
2. **LLM check** (optional, when planner is configured): Assesses whether the description is unambiguous enough for autonomous execution.

If the check fails:
- A structured comment is posted to the issue listing missing fields and questions.
- The `needs-clarification` label is applied.
- The issue is skipped until the user replies.

When the user replies (any comment after the bot's clarification request):
- The `needs-clarification` label is automatically removed.
- The issue re-enters the candidate pool on the next poll cycle.
- A second triage runs; if still incomplete, the cycle repeats.

### What the Daemon Must NOT Do

- Must not consume parent/epic issues.
- Must not set Done unless gate + merge confirmed.
- Must not execute issues with `needs-clarification` label.
- Must not rely on board position or UI layout for decisions.

## 5. Issue Description Template

Every executable issue entering Ready must contain:

```markdown
## Goal
[Single paragraph: what this issue accomplishes]

## Non-Goals
[What this issue explicitly does NOT do]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Files in Scope
- `path/to/file.py`

## Test Requirements
- All existing tests must pass
- [Specific new tests if applicable]

## Merge Constraints
- PR required, no direct push to main
- Gate evaluation must pass before merge
```

### Minimum Completeness

An issue without these fields should not be moved to Ready or labeled `agent-ready`:
- Goal (non-empty)
- At least one acceptance criterion
- At least one file in scope or explicit "any" scope

## 6. API vs. UI Boundary

### API Manages (Truth Layer)

- Issues, projects, labels, parent-child relationships
- Workflow state transitions
- Comments and attachments
- Label-driven routing logic
- Webhook event consumption

### UI Manages (Display Layer)

- Custom views (Roadmap view, Agent view, Review view)
- Filters and saved filter sets
- Board vs. list layout
- Column grouping and ordering
- Card display fields

### Recommended Views (configure manually in Linear UI)

1. **Roadmap View**: Group by Project, show parent issues, track epic progress.
2. **Agent Execution View**: Filter `state in (Ready, In Progress, In Review)` + label `agent-ready` + exclude `epic`. Board grouped by Status.
3. **Review Queue View**: Filter `state == In Review`. Grouped by assignee.
4. **Blocked / Triage View**: Filter label `blocked` or `needs-clarification`.

## 7. PromotionService Convention

When `spec-orch promote` creates Linear issues from a plan:

1. Each work packet becomes an executable issue.
2. Auto-labeled with `task` + `agent-ready`.
3. Set as child of the relevant Epic (if found).
4. Description follows the template in Section 5.
5. Issues land in Backlog; human or automation moves to Ready.

## 8. Generalization

This convention is designed to be project-agnostic. To adopt it for a new project:

1. Create the workflow states (Backlog, Ready, In Progress, In Review, Done, Canceled).
2. Create the label set (type + qualification labels).
3. Set up the `[daemon]` section in `spec-orch.toml`.
4. Configure 2-4 views in Linear UI.
5. Follow the three-layer object model for issue hierarchy.
