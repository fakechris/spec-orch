# EODF 端到端开发闭环操作指引

> End-to-End Development Flow with ACPX + OpenCode + MiniMax

本文档记录了使用 spec-orch 的 ACPX adapter 通过 OpenCode agent 和 MiniMax 模型完成一次完整的端到端开发闭环（EODF）的每一步操作。

---

## 0. 前置条件

### 环境要求

| 依赖 | 验证命令 | 说明 |
|------|---------|------|
| Python 3.11+ | `python3 --version` | spec-orch 运行时 |
| Node.js + npx | `npx --version` | ACPX 通过 npx 运行 |
| OpenCode | `which opencode` | ACPX 调用的底层 agent |
| Git | `git --version` | worktree 管理 |
| GitHub CLI | `gh --version` | PR 创建和 CI 检查 |
| spec-orch | `spec-orch --version` | 已安装到 PATH |

### 环境变量

```bash
# Linear API token（用于 issue 管理）
export SPEC_ORCH_LINEAR_TOKEN="lin_api_xxxxx"

# MiniMax API key（OpenCode 通过此 key 调用 MiniMax 模型）
export MINIMAX_API_KEY="sk-cp-xxxxx"
```

### spec-orch.toml 配置

可以用 `spec-orch init` 自动生成基础配置，然后手动调整 builder 段为 ACPX：

```bash
spec-orch init  # 如果还没有 spec-orch.toml
```

确保 `spec-orch.toml` 包含以下配置：

```toml
[issue]
source = "linear"

[verification]
lint = ["{python}", "-m", "ruff", "check", "src/"]
typecheck = ["{python}", "-m", "mypy", "src/"]
test = ["{python}", "-m", "pytest", "-q"]
build = ["{python}", "-c", "print('build ok')"]

[builder]
adapter = "acpx"
agent = "opencode"
model = "minimax/MiniMax-M2.5"
timeout_seconds = 1800
```

验证配置：

```bash
spec-orch config check
# 期望输出:
# [PASS] builder: adapter=acpx, agent=opencode, model=minimax/MiniMax-M2.5
```

> 配置详情参见 [AI Config Guide](ai-config-guide.md)，包含各语言的模板。

---

## 1. 创建 Linear Issue

在 Linear 中创建一个小需求 issue。可以通过 Linear UI 或 CLI 创建。

### 通过 Python 脚本创建

```bash
python3 -c "
from spec_orch.services.linear_client import LinearClient
c = LinearClient()
issue = c.create_issue(
    team_key='SON',
    title='status 命令增强: 显示 flow type + adapter/agent 配置',
    description='''## 目标
增强 spec-orch status 命令输出...

## 范围
- 修改 src/spec_orch/cli.py 中的 status 子命令
''',
)
print(f'Created: {issue[\"identifier\"]}')
print(f'UUID: {issue[\"id\"]}')
"
```

**记录**：Issue ID（如 `SON-157`）和 UUID（如 `f21cd940-...`）。

### 设置状态为 Ready

```bash
python3 -c "
from spec_orch.services.linear_client import LinearClient
c = LinearClient()
c.update_issue_state('<UUID>', 'Ready')
print('Done')
"
```

---

## 2. 运行 EODF Pipeline

### 执行命令

```bash
spec-orch run SON-157 -s linear --live
```

参数说明：
- `SON-157`：Linear issue ID
- `-s linear`：从 Linear API 加载 issue（而非本地 fixture）
- `--live`：实时输出到 stderr

### Pipeline 内部流程

执行后 spec-orch 自动完成以下步骤：

```
1. [RUN]     创建 git worktree: .worktrees/SON-157/
2. [SPEC]    保存 spec snapshot（从 issue description 提取）
3. [BUILDER] 调用 ACPX adapter:
             npx -y acpx --format json --approve-all \
               --model minimax/MiniMax-M2.5 \
               opencode exec "<builder_prompt>"
             ↓ OpenCode 使用 MiniMax 模型在 worktree 中编码
             ↓ 生成 builder_report.json
4. [VERIFY]  运行验证:
             - lint: ruff check
             - typecheck: mypy
             - test: pytest
             - build: pip install
5. [REVIEW]  初始化 review（本地模式: pending）
6. [GATE]    评估 gate 条件:
             - builder: 是否成功
             - verification: 是否全部通过
             - review: 是否 approved
             - human_acceptance: 是否人工确认
```

### 预期耗时

| 阶段 | 典型耗时 |
|------|---------|
| ACPX/OpenCode 初始化 | ~5s |
| MiniMax 编码 | 3-8 min |
| 验证 | ~30s |
| 总计 | 4-9 min |

### 检查 Builder 结果

```bash
# 查看 builder 报告
cat .worktrees/SON-157/builder_report.json | python3 -m json.tool

# 查看 builder 修改了哪些文件
cd .worktrees/SON-157 && git diff --stat main

# 查看具体代码变更
cd .worktrees/SON-157 && git diff main -- src/
```

---

## 3. 验证 Builder 产出

### 手动验证代码质量

```bash
cd .worktrees/SON-157

# Lint
python3 -m ruff check src/ tests/

# Type check（针对修改的文件）
python3 -m mypy src/spec_orch/cli.py

# 运行相关测试
python3 -m pytest tests/unit/ -v --tb=short
```

> 注意：typecheck 和 test 的 FAILED 可能是预先存在的问题（如缺少
> optional deps 的类型存根），不一定是 builder 引入的。需要区分。

---

## 4. 整合代码到 Feature Branch

### 创建 feature 分支

```bash
cd /path/to/spec-orch  # 主 worktree
git checkout main && git pull origin main
git checkout -b feat/eodf-son-157
```

### 应用 Builder 的改动

两种方式：

**方式 A：直接复制修改的文件**

```bash
cp .worktrees/SON-157/src/spec_orch/cli.py src/spec_orch/cli.py
```

**方式 B：手动 cherry-pick（如果 builder 有提交）**

```bash
git cherry-pick <commit-hash>
```

> 推荐方式 A，因为可以同时加入自己的修改和文档。

### 运行测试确认

```bash
python3 -m pytest tests/unit/ -v --tb=short
python3 -m ruff check src/ tests/
python3 -m ruff format --check src/ tests/
```

---

## 5. 提交并创建 PR

### Commit

```bash
git add -A
git commit -m "feat: status 命令显示 flow type + adapter 信息 (SON-157)

由 OpenCode/MiniMax 通过 ACPX pipeline 实现。
"
```

### Push + PR

```bash
git push -u origin feat/eodf-son-157

gh pr create \
  --title "feat: status 命令增强 + EODF 过程指引 (SON-157)" \
  --body "## Summary
- status 命令显示 flow type 和 builder adapter 信息
- 新增 EODF 端到端操作指引文档

## EODF Validation
Builder: ACPX + OpenCode + MiniMax-M2.5
"
```

---

## 6. CI Review + Merge

### 等待 CI

```bash
# 查看 CI 状态
gh pr checks <PR-NUMBER>

# 等待所有 checks 通过后合并
gh pr merge <PR-NUMBER> --squash --delete-branch
```

### 预期 CI 矩阵

| Check | 说明 |
|-------|------|
| lint (3.11/3.12/3.13) | ruff check + format |
| test (ubuntu/macos × 3.11/3.12/3.13) | pytest |
| typecheck | mypy |
| build | pip install |
| CodeRabbit / Devin Review | 自动 code review |

---

## 7. 更新 Linear Issue

```bash
python3 -c "
from spec_orch.services.linear_client import LinearClient
c = LinearClient()
c.update_issue_state('<UUID>', 'Done')
print('Issue closed')
"
```

---

## 8. 清理

```bash
# 删除 worktree
git worktree remove .worktrees/SON-157 --force

# 删除本地分支（如果还存在）
git branch -D issue/son-157
```

---

## 常见问题

### Q: Builder 报 "No acpx session found"

ACPX 默认使用 persistent session 模式。spec-orch 的 ACPX adapter 已配置为使用
`exec` 子命令（一次性执行），不需要预创建 session。如果仍出现此错误，检查
`acpx_builder_adapter.py` 的 `_build_command` 方法是否包含 `exec` 子命令。

### Q: SSL ConnectError

网络不稳定时 Linear API 调用可能失败。等待几秒后重试：

```bash
# 清理后重试
git worktree remove .worktrees/SON-XXX --force
git branch -D issue/son-xxx
sleep 10
spec-orch run SON-XXX -s linear --live
```

### Q: report_path 路径翻倍

如果看到类似 `.worktrees/SON-XXX/.worktrees/SON-XXX/builder_report.json`
的错误路径，这是 v0.5.0 的已知 bug，在 PR #71 中已修复。确保使用最新代码。

### Q: Verification 中 typecheck/test 失败

区分是 builder 引入的还是预先存在的：

```bash
# 只检查 builder 修改的文件
cd .worktrees/SON-XXX
git diff --name-only main | grep '\.py$' | xargs python3 -m mypy
```

---

## 架构参考

EODF 闭环体现了 spec-orch 的 Orchestration 模式（非 Multi-Agent）：

```
spec-orch (orchestrator)
  ├─ Linear API → 加载 issue（输入）
  ├─ ACPX adapter → spawn OpenCode sub-agent（fire-and-forget）
  │   └─ OpenCode + MiniMax → 在 worktree 中编码（独立执行）
  ├─ Verification → 代码强制检查（gate script）
  ├─ Review → 自动/人工审查
  └─ Gate → 代码强制的合并条件
```

正如文章所说：**Prompt 是建议，代码是强制。** spec-orch 的 gate、verification、
worktree 隔离都是代码层面的强制约束，而非 prompt 层面的"建议"。Builder agent
在确定性轨道上执行，orchestrator 只收报告、做决策。
