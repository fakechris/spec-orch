# Planning Convention

spec-orch uses a **layered authority** model — different types of information live in different places.

## Source of Truth

| Information | Authority | Location |
|-------------|-----------|----------|
| Strategic decisions & ADRs | **Repo** | `docs/plans/`, `docs/architecture/` |
| Feature specs (what to build) | **Repo** | `docs/specs/<mission-id>/spec.md` |
| Execution plan & priority | **Linear** | Project kanban, Epic hierarchy |
| Task status (todo/doing/done) | **Linear** | Issue workflow states |

**Principle: Spec in Repo, Plan in Linear.**

## Information Flow

```
Brainstorm (CLI / Linear comment / Slack)
    ↓ @freeze
Spec  →  docs/specs/<id>/spec.md          (canonical contract, versioned)
    ↓ approve + plan
Plan  →  docs/specs/<id>/plan.json        (execution DAG, versioned)
    ↓ promote
Issues →  Linear (SON-xx)                  (kanban tracking, authoritative)
    ↓ daemon / manual
Code + PR + Done                           (writeback to Linear)
```

The flow is **unidirectional**: Repo → Linear. Status flows back only as
`completed_at` timestamps on `mission.json`.

## Linear Structure

```
Project: spec-orch
 ├── Epic: Gate-as-a-Layer (SON-37)
 ├── Epic: EODF 自动化闭环 (SON-41)
 ├── Epic: Daemon & 持续运行 (SON-44)
 ├── Epic: 开发者体验 (SON-48)
 └── Epic: 多渠道讨论 & 远程协作 (SON-52)
```

Each Epic is a parent issue. Feature issues are children of their Epic.

## When to Use Each System

| Action | Where |
|--------|-------|
| Brainstorming a new feature | `spec-orch discuss` or Linear comment |
| Writing the specification | `docs/specs/<id>/spec.md` in repo |
| Prioritizing what's next | Linear kanban — drag issues |
| Choosing what daemon runs | Linear Todo column (daemon polls this) |
| Recording architecture decisions | `docs/plans/` or `docs/architecture/` |
| Reviewing progress | Linear project board or `spec-orch dashboard` |

## Daemon Convention

The daemon treats **Linear as the authoritative task queue**:

1. Polls Linear for issues in **Todo** state
2. Moves to **In Progress** on pickup
3. Executes the build pipeline
4. On success: creates PR, moves to **Done**
5. On failure: adds comment, leaves in **In Progress** for triage

## Creating New Work

For EODF-driven features:

```bash
spec-orch discuss             # brainstorm → @freeze → spec
spec-orch mission approve     # approve the spec
spec-orch plan <mission-id>   # generate execution plan
spec-orch promote <mission-id> # create Linear issues from plan
# → issues appear in Linear Backlog
# → drag to Todo when ready to execute
```

For quick fixes or direct development:

```bash
# Create issue directly in Linear
# Work on feature branch
# PR → merge → close issue
```
