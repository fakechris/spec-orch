---
name: spec-orch-mr-closed-loop
description: >-
  Enforces the Spec-orch delivery loop in this repo: local verify → MR → read
  review comments (not only CI) → fix → merge when green → pick next Linear work.
  Use when shipping code changes, continuing epic work, "MR 闭环", "merge after
  CI", "review 修完再合", or when the user asks to run the full delivery cycle
  without stopping at green CI only.
---

# Spec-orch MR 闭环（Cursor / Agent）

本 Skill 与 **`spec-orch-spec-stage`** **不重复**：后者管 Spec 阶段与 CLI 状态机；本 Skill 管 **代码合入主线** 的闭环。

与 **`sp-verification-before-completion`** **互补**：后者强调「宣称完成前要有证据」；本 Skill 把 **0→5** 串成固定节奏，并强制 **人工/bot Review 可读性**（不能只看 CI）。

## 何时必须启用

- 用户说：继续开发、收尾、开 MR、合进 main、按闭环走、不要只盯 CI。
- 任意非琐碎改动准备进 `main` 时。

## 闭环步骤（必须按顺序）

### 0 — 本地验证（再推远程）

在推送前执行（或项目约定的等价命令）：

- `ruff format` / `ruff check`（或 `make lint`）
- `mypy`（若项目启用）
- `pytest`：至少覆盖本次改动相关用例；全量失败时区分 **本次引入** vs **环境/既有 flaky**

**禁止**：未跑本地检查就推 MR（除非用户明确豁免）。

### 1 — 提交 MR

- 从 `main` 拉最新，建分支 `feat/<issue-id>-<slug>` 或 `fix/...`。
- 提交信息写清动机；关联 Linear issue ID（若适用）。
- `git push -u origin <branch>`，用 `gh pr create`（或 Web）开 PR，描述里写 **测了什么、风险、回滚**。

### 2 — 等待并查看 Review

- 用 `gh pr view <n> --comments`、`gh api` 拉 **review 评论**、CodeRabbit 等 bot 评论。
- **必须阅读** review 正文，不是只看 ✅。

### 3 — Review 后自动修复一轮

- 对 **每一条可执行** 的 review 意见：要么改代码，要么在 PR 里回复 **为何不采纳**（附理由）。
- 再推 commit；若涉及设计分歧，简短同步用户（仅当阻塞）。

### 4 — CI 绿后再合并

- `gh pr checks <n>` 或 Actions 页：全部通过。
- 若有 merge 冲突：先 `main` 合并进分支或 rebase，再跑步骤 0 再推。
- `gh pr merge <n> --squash`（或团队约定的方式）。
- **禁止**：仅因「没有评论」就合并；**禁止**：忽略未解决的 review thread（若平台有 thread 状态）。

### 5 — Linear 下一步

- 合并后打开 Linear（或 API）：当前 Epic 下 **下一个** 就绪 issue（依优先级 / 依赖）。
- 把新分支名、PR 与 issue 对齐，再从此 Skill 的步骤 0 开始下一轮。

## 与现有 Cursor Skills 的关系

| Skill | 关系 |
|-------|------|
| `spec-orch-spec-stage` | Spec/问题/批准；**不**替代 MR 闭环。 |
| `sp-verification-before-completion` | 强调验证证据；本 Skill 的步骤 **0** 应满足其精神。 |
| `sp-finishing-a-development-branch` | 合并策略与收尾选项；本 Skill 的步骤 **4–5** 可引用其决策框架。 |
| `sp-receiving-code-review` | 质疑不清的 review；步骤 **3** 遇到模糊意见时用。 |

## Agent 自检（每次合并前回答）

1. 我是否读过 **PR 评论与 review**，而不只是 CI？
2. 本次改动是否 **有测试或证据** 支撑？
3. 合并后 **Linear 下一项** 是否已更新/已认领？

任一否 → 先补全再合并。

## 命令速查（GitHub CLI）

```bash
gh pr create --fill --base main
gh pr checks <PR>
gh pr view <PR> --comments
gh pr merge <PR> --squash --delete-branch
```

## Linear 速查

- 浏览器：项目视图 → Epic → 下一 issue。
- 若有 `SPEC_ORCH_LINEAR_TOKEN`：可用仓库内 `LinearClient` 脚本或 MCP（若配置）查询；**不要**把 token 写进 Skill 或日志。
