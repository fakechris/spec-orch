# Planning Convention

spec-orch uses a **layered authority** model — different types of information live in different places.

> See also: [Change Management Policy](docs/architecture/change-management-policy.md)
> for the three-tier workflow (Full / Standard / Hotfix).

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
Brainstorm (CLI TUI / Linear comment / Slack)
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
| Signalling readiness for daemon | Drag issue to **Ready** column in Linear |
| Recording architecture decisions | `docs/plans/` or `docs/architecture/` |
| Reviewing progress | Linear project board or `spec-orch dashboard` |

## Daemon Convention

The daemon treats **Linear as the authoritative task queue**:

1. Polls Linear for issues in **Ready** state (configurable via `consume_state`)
2. Runs **readiness triage** — rule-based + LLM check on issue completeness; if underspecified, posts clarification questions on Linear and adds `needs-clarification` label
3. Moves to **In Progress** on pickup
4. Executes the build pipeline (Codex build → verification → review → gate)
5. Checks **merge readiness** (`git merge-tree` dry-run, auto-rebase if needed)
6. On success: creates PR, moves to **In Review**
7. **Review loop**: monitors PRs for new commits; when fixes are pushed, re-runs verification + gate
8. On merge: Linear-GitHub App auto-closes the issue to **Done**
9. On failure: adds comment with error details, leaves in **In Progress** for triage

Labels that affect daemon behaviour:
- `needs-clarification` — issue excluded from processing until user responds
- `blocked` — issue excluded from processing
- `hotfix` — (future) priority queue + minimal gate profile

## Change Tiers

Not all work follows the full EODF pipeline. See the
[Change Management Policy](docs/architecture/change-management-policy.md)
for the complete specification. Summary:

| Tier | When | Minimum Steps |
|------|------|---------------|
| **Full** | New features, architecture | All 11 EODF pipeline steps |
| **Standard** | Bug fixes, improvements | issue → branch → fix → PR → review → merge |
| **Hotfix** | Production blockers | issue → branch → fix → PR → merge (review post-merge) |

**Hard rule: no direct push to main.** Enforced by GitHub branch protection.

## Creating New Work

For EODF-driven features (Full tier):

```bash
spec-orch discuss             # brainstorm → @freeze → spec
spec-orch mission approve     # approve the spec
spec-orch plan <mission-id>   # generate execution plan
spec-orch promote <mission-id> # create Linear issues from plan
# → issues appear in Linear Backlog
# → drag to Ready when ready to execute
```

For bug fixes and improvements (Standard tier):

```bash
# Create issue in Linear with Bug or Improvement label
# Create branch, implement fix
# Create PR linking the issue
# Review → merge → issue auto-closes
```
