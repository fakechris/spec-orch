# SpecOrch Pipeline: Stages, Roles, and Responsibilities

## Role Definitions

| Role | Identity | Tools / Implementation |
|------|----------|----------------------|
| **Human** | User / product owner | Linear UI, CLI, Slack |
| **Planner** | LLM-based solution designer | LiteLLM (MiniMax M2.5, etc.) |
| **Orchestrator** | Pipeline coordinator (daemon / CLI) | `spec-orch` daemon + RunController |
| **Builder** | Code generation executor | Codex / Claude Code |
| **Verifier** | Automated validation runner | lint, typecheck, test, build (subprocess) |
| **Reviewer** | Code review engine | GitHub review bots (Devin, Gemini, CodeRabbit, Codex) |
| **Gate** | Merge-readiness evaluator | GateService + GatePolicy |
| **Git/GitHub** | Version control + PR platform | git CLI, gh CLI |
| **Linear** | Task control plane | Linear GraphQL API |

## End-to-End Pipeline

```mermaid
flowchart TD
    subgraph phase1 ["Phase 1: Discussion"]
        H1["Human: Raise idea / requirement"]
        P1["Planner: Brainstorming dialogue"]
        F1["Human: @freeze to finalise discussion"]
    end

    subgraph phase2 ["Phase 2: Contract"]
        M1["Orchestrator: Generate spec.md + mission.json"]
        H2["Human: spec-orch mission approve"]
        P2["Planner: spec-orch plan → ExecutionPlan"]
        H3["Human: Review plan → spec-orch promote"]
    end

    subgraph phase3 ["Phase 3: Execution"]
        O1["Orchestrator: Create Linear issues + isolated worktree"]
        B1["Builder: Codex builds code"]
        V1["Verifier: lint / typecheck / test / build"]
        R1["Reviewer: Code review"]
        G1["Gate: Evaluate merge conditions"]
    end

    subgraph phase4 ["Phase 4: Delivery"]
        MR1["Orchestrator: Merge-readiness check"]
        RB1["Git: Auto rebase"]
        RB2["Builder: Conflict resolution"]
        PR1["Orchestrator: Create GitHub PR"]
        RV1["Reviewer: PR review"]
        FIX1["Builder / Human: Fix review findings"]
        RL1["Orchestrator: Review-loop detects new push"]
    end

    subgraph phase5 ["Phase 5: Closure"]
        MG1["Gate / GitHub: Merge PR"]
        LN1["Linear: Issue → Done"]
        RT1["Orchestrator: Retrospective"]
    end

    H1 --> P1 --> F1 --> M1 --> H2 --> P2 --> H3
    H3 --> O1 --> B1 --> V1 --> R1 --> G1
    G1 --> MR1
    MR1 -->|"No conflicts"| PR1
    MR1 -->|"Conflicts detected"| RB1
    RB1 -->|"Rebase succeeded"| PR1
    RB1 -->|"Rebase failed"| RB2
    RB2 --> PR1
    PR1 --> RV1
    RV1 -->|"Approved"| MG1
    RV1 -->|"Changes requested"| FIX1
    FIX1 --> RL1
    RL1 -->|"New commit detected"| V1
    MG1 --> LN1 --> RT1
```

## Stage Details

### Phase 1: Discussion

| Step | Primary Role | Input | Output | Options |
|------|-------------|-------|--------|---------|
| Raise requirement | **Human** | Idea / problem | Natural language description | CLI TUI / Slack / Linear comment |
| Brainstorm | **Planner** | Conversation history | Solution exploration | `spec-orch discuss` |
| Freeze discussion | **Human** | `@freeze` command | spec.md draft + mission.json | In-session command |

### Phase 2: Contract

| Step | Primary Role | Input | Output | Options |
|------|-------------|-------|--------|---------|
| Approve spec | **Human** | spec.md | mission.json.approved_at | `spec-orch mission approve` |
| Generate execution plan | **Planner** | spec.md + codebase | plan.json (waves + packets) | `spec-orch plan` |
| Promote to Linear | **Orchestrator** | plan.json | Linear issues (one per packet) | `spec-orch promote` |

### Phase 3: Execution

| Step | Primary Role | Input | Output | Options |
|------|-------------|-------|--------|---------|
| Readiness assessment | **Orchestrator** | Issue description | ready / needs-clarification | ReadinessChecker (rules + LLM) |
| Code build | **Builder** | spec + issue prompt | Code changes | Codex CLI (`codex exec`) |
| Automated verification | **Verifier** | Workspace code | lint / test / build results | subprocess execution |
| Automated review | **Reviewer** | PR diff | Review verdict + findings | LocalReviewAdapter / GitHubReviewAdapter |
| Gate evaluation | **Gate** | All conditions | mergeable / blocked | GatePolicy + profiles |

### Phase 4: Delivery

| Step | Primary Role | Input | Output | Failure Handling |
|------|-------------|-------|--------|-----------------|
| Merge check | **Git** | branch vs main | conflict / clean | `git merge-tree` dry-run |
| Auto rebase | **Git** | branch + main | rebased branch | `git rebase` + `--force-with-lease` |
| Conflict resolution | **Builder** *(not yet implemented)* | conflict markers | resolved code | Codex executes resolve task |
| Create PR | **Orchestrator** | workspace | GitHub PR URL | `gh pr create` |
| PR review | **Reviewer** | PR diff | review comments | Devin / Gemini / CodeRabbit / Codex bots |
| Fix review findings | **Human** or **Builder** | review comments | new commits | manual or automated |
| Review loop | **Orchestrator** | PR headRefOid | re-run verify + gate | daemon polls for new commits |

### Phase 5: Closure

| Step | Primary Role | Input | Output | Trigger |
|------|-------------|-------|--------|---------|
| Merge PR | **Gate** + **GitHub** | gate pass | merged code | auto-merge or manual |
| Close issue | **Linear** | PR merged | issue → Done | Linear-GitHub App |
| Retrospective | **Orchestrator** | run artifacts | retrospective.md | `spec-orch retro` |

## Conflict Resolution Decision Tree

```mermaid
flowchart TD
    Start["Pre-PR creation"] --> Check["git merge-tree dry-run"]
    Check -->|"Clean"| CreatePR["Create PR directly"]
    Check -->|"Conflicts"| Rebase["git rebase origin/main"]
    Rebase -->|"Success"| Push["git push --force-with-lease"]
    Push --> CreatePR
    Rebase -->|"Failure"| Classify["Classify conflict type"]
    Classify -->|"Formatting / import conflicts"| AutoResolve["Builder: auto-resolve"]
    Classify -->|"Logic / semantic conflicts"| LLMResolve["Planner: analyse + Builder: implement"]
    Classify -->|"Architecture-level conflicts"| HumanEscalate["Notify Human for intervention"]
    AutoResolve --> ReVerify["Verifier: re-run validation"]
    LLMResolve --> ReVerify
    HumanEscalate --> ReVerify
    ReVerify --> CreatePR
```

**Current implementation status:**

| Capability | Status |
|-----------|--------|
| `git merge-tree` dry-run | Implemented |
| `git rebase` | Implemented |
| Classify conflict type after rebase failure | **Not implemented** (current: create PR with warning) |
| Builder auto-resolve | **Not implemented** |
| Planner-assisted resolve | **Not implemented** |
| Human escalation | **Not implemented** |

## Review-Fix Loop Sequence

```mermaid
sequenceDiagram
    participant D as Daemon
    participant GH as GitHub
    participant R as Reviewer Bots
    participant V as Verifier
    participant G as Gate
    participant L as Linear

    D->>GH: create PR (draft or non-draft)
    D->>L: issue → In Review
    D->>D: _pr_commits[issue] = HEAD SHA
    D->>D: _processed.add(issue)

    R->>GH: post review comments
    Note over GH: Human or Builder pushes fix commits

    loop Each poll cycle
        D->>GH: list_open_prs() → get headRefOid
        alt SHA changed
            D->>D: _processed.remove(issue)
            D->>L: issue → Ready (consume_state)
            Note over D: Next poll re-picks issue
            D->>V: Re-run verification
            V->>G: Re-evaluate gate
            G->>GH: Update gate status
        else SHA unchanged
            Note over D: Skip
        end
    end
```
