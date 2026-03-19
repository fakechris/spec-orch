# SpecOrch

[![CI](https://github.com/fakechris/spec-orch/actions/workflows/ci.yml/badge.svg)](https://github.com/fakechris/spec-orch/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/spec-orch)](https://pypi.org/project/spec-orch/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/spec-orch)](https://pypi.org/project/spec-orch/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Spec 驱动的软件交付控制面。**

> [English README](README.md) | [Project Vision](VISION.md) / [项目愿景](VISION.zh.md)

SpecOrch 用 spec 优先、gate 优先、证据驱动的方式编排 AI 编码代理。它把 **意图、任务、执行、验证、进化** 串成一个统一的控制面——让你从"盯着 agent 干活"变成"运营一套交付系统"。

**不是聊天工具。不是多智能体实验场。不是 IDE。**

而是一个让软件交付变得可编排、可验证、可自我改进的控制面。

## 核心洞察

> **Issue 不是需求——Spec 才是需求。**
> **Merge 不是完成——Gate 才是完成。**
> **编排不是静态的——它随每次运行而进化。**
> **Prompt 是建议——Harness 是强制。**

## 七层架构

SpecOrch 将完整交付生命周期组织为七个平面：

```
┌──────────────────────────────────────────────────────┐
│  进化层    traces → evals → harness 改进             │
├──────────────────────────────────────────────────────┤
│  控制层    mission / session / PR / gate 运营         │
├──────────────────────────────────────────────────────┤
│  证据层    findings / tests / review / gate           │
├──────────────────────────────────────────────────────┤
│  执行层    worktree / sandbox / agent 适配            │
├──────────────────────────────────────────────────────┤
│  装配层    上下文契约 / skills / policies              │
├──────────────────────────────────────────────────────┤
│  任务层    计划 DAG / 波次 / 工作包                    │
├──────────────────────────────────────────────────────┤
│  契约层    spec / scope / 验收标准 / 冻结             │
└──────────────────────────────────────────────────────┘
```

| 平面 | 职责 |
|------|------|
| **契约层** | 冻结 spec——要做什么、边界、验收标准 |
| **任务层** | 将 spec 展开为含依赖的可执行任务图 |
| **装配层** | 让执行变稳定：上下文契约、策略、钩子、反应机制 |
| **执行层** | 在隔离 worktree/sandbox 中用可插拔 agent 运行每个任务 |
| **证据层** | 证明完成：门控评估、发现、偏差、审查 |
| **控制层** | 运营系统：mission、session、PR、仪表盘 |
| **进化层** | 从证据学习：进化 prompt、规则、策略、policy |

详见 [Seven Planes 架构映射](docs/architecture/seven-planes.md)。

## 用户故事：从想法到合并代码

### 1. 讨论和起草 Spec（契约层）

```bash
spec-orch discuss
# 交互式 TUI 头脑风暴 — 输入 @freeze 冻结为 spec
```

或直接创建 Mission：

```bash
spec-orch mission create "WebSocket 实时通知"
spec-orch mission approve websocket-real-time-notifications
```

### 2. 生成执行计划（任务层）

```bash
spec-orch plan websocket-real-time-notifications
# 输出: 4 个波次, 7 个工作包
```

波次按序执行；波次内的工作包可并行。

### 3. 执行（执行层）

**一次性 CLI：**

```bash
spec-orch run SON-20 --source linear --auto-pr
```

完整流水线：加载 issue → 规划 → 构建 → 验证 → 审查 → 门控 → PR → Linear 回写。

**Daemon 模式——全自主：**

```bash
spec-orch daemon start --config spec-orch.toml --repo-root .
```

轮询 Linear → 就绪分诊 → 构建 → 验证 → 门控 → PR → 审查循环。

**Mission 模式：**

```bash
spec-orch run-plan websocket-real-time-notifications
```

### 4. 人工验收（证据层）

```bash
spec-orch accept-issue SON-20 --accepted-by chris
```

你验证的是 **结果是否符合 spec**——合规检查清单和偏差摘要，而非看原始 diff。

### 5. 复盘（进化层）

```bash
spec-orch retro websocket-real-time-notifications
```

从运行证据生成复盘。系统学习并改进下一个周期。

## 核心组件

### 可插拔 Agent 适配器

| 适配器 | Agent | 协议 |
|--------|-------|------|
| `codex_exec` | OpenAI Codex | `codex exec --json` |
| `opencode` | OpenCode | JSONL 事件流 |
| `claude_code` | Claude Code | stream-json |
| `droid` | Factory Droid | ACP 事件 |
| `acpx` | 15+ agents | Agent Client Protocol |

只需改 `spec-orch.toml` 的一行即可切换 agent：

```toml
[builder]
adapter = "acpx"
agent = "opencode"
model = "minimax/MiniMax-M2.5"
```

### 门控系统

可配置的合并条件与 profile（full / standard / hotfix）：

```bash
spec-orch gate evaluate SON-20    # 评估所有条件
spec-orch gate show-policy        # 打印门控策略
spec-orch explain SON-20          # 人类可读的门控报告
```

### 自进化引擎

系统在每次运行后自我改进：

```bash
spec-orch evidence summary        # 历史运行模式分析
spec-orch harness synthesize      # 自动生成合规规则
spec-orch prompt evolve           # A/B 测试 prompt 变体
spec-orch strategy analyze        # 学习 scoper 提示
spec-orch policy distill          # 零 LLM 确定性脚本
```

## 当前状态

**v0.5.1** — Alpha，吃自己的狗粮（EODF）模式。

系统用自己来开发自己，每次迭代都在自我改进。900+ 测试，65+ 命令。

`main` 分支已有的功能：

- 七层架构 + 闭环进化
- 可插拔 builder/reviewer 适配器（Codex、OpenCode、Claude Code、Droid、ACPX）
- ACPX 统一适配器，通过 Agent Client Protocol 包装 15+ agents
- Fixture 或 Linear 支持的 issue 加载，可配置 issue 源
- 每 issue 独立 git worktree 隔离
- 可配置验证（lint、typecheck、test、build），按项目类型定制
- 门控评估 + profile（full / standard / hotfix）
- YAML 定义的 agent 行为合规引擎
- Daemon 模式：就绪分诊、审查循环、merge 检查、重试
- GitHub PR 自动创建，gate 作为 commit status
- Spec 偏差跟踪与结构化发现
- 三级变更管理（Full / Standard / Hotfix）
- Web 仪表盘 + Rich TUI（TypeScript/React/Ink）
- Mission Control Center + EventBus
- Conductor 渐进形式化
- 跨 session 记忆
- 完整自进化：证据分析、harness 合成、prompt 进化、policy 蒸馏
- `spec-orch init` 项目类型检测和配置生成
- 低成本模型支持（MiniMax-M2.5，~$0.04/run）

## 安装

### 快速开始

```bash
# 1. 安装
git clone https://github.com/fakechris/spec-orch.git
cd spec-orch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. 配置环境变量 — 复制并编辑 .env
cp .env.example .env
# 编辑 .env：设置 SPEC_ORCH_LLM_API_KEY 和 SPEC_ORCH_LLM_API_BASE
# (详见 .env.example 中的各提供商配置示例)

# 3. 初始化项目配置
spec-orch init                    # LLM 优先检测（自动回退 rules）
spec-orch init --offline          # 强制规则检测
spec-orch init --reconfigure      # 重新检测并覆盖已有配置

# 4. 验证一切正常
spec-orch config check            # 验证配置
spec-orch discuss                 # 测试 LLM 连通性（交互式 TUI）
```

**必需的环境变量**（在 `.env` 中设置或 export）：

| 变量 | 用途 | 示例 |
|------|------|------|
| `SPEC_ORCH_LLM_API_KEY` | LLM 提供商 API key（planner、discuss、triage） | `sk-ant-xxx` 或 MiniMax key |
| `SPEC_ORCH_LLM_API_BASE` | LLM API 端点 | `https://api.anthropic.com` |
| `SPEC_ORCH_LINEAR_TOKEN` | Linear issue 跟踪（daemon 模式需要） | `lin_api_xxx` |

完整配置参考见 [`.env.example`](.env.example)。

### 通过 pip / uv 从 GitHub 安装

```bash
pip install "spec-orch @ git+https://github.com/fakechris/spec-orch.git"
uv pip install "spec-orch @ git+https://github.com/fakechris/spec-orch.git"
```

### 从 PyPI 安装

```bash
pip install spec-orch
pip install "spec-orch[all]"
```

### 验证

```bash
spec-orch --version   # 0.5.1
spec-orch config check
```

### 环境要求

- **Python 3.11+**（3.11、3.12、3.13 已测试）
- **Git**（用于 worktree 隔离）
- **Builder CLI** — Codex、OpenCode、Droid、Claude Code 或任何 ACPX 兼容 agent
- **Linear API token**（可选，用于 issue 跟踪）
- **LLM API key**（可选，用于规划 / 审查 / 分诊）

### 可选依赖

| Extra | 包 | 用途 |
|-------|------|------|
| `planner` | litellm | `discuss`、`plan`、就绪分诊 |
| `dashboard` | fastapi, uvicorn | `spec-orch dashboard` |
| `slack` | slack-bolt | Slack 讨论适配 |
| `all` | 以上全部 | 完整功能 |
| `dev` | all + pytest, ruff, mypy, build, twine | 开发 |

## 配置

SpecOrch 通过 `spec-orch.toml` 配置。运行 `spec-orch init` 自动检测项目并生成配置：

```bash
spec-orch init               # LLM 优先检测，失败自动回退规则检测
spec-orch init --offline     # 强制规则检测
spec-orch init --reconfigure # 重新检测并覆盖已有配置
spec-orch init --force       # 强制覆盖已有配置
```

`spec-orch init` 会把检测模式写入 `spec-orch.toml` 的
`[init].detection_mode`，用于后续重配时保持可复现行为。

详见 [spec-orch.toml 参考](docs/reference/spec-orch-toml.md) 和 [AI 配置指南](docs/guides/ai-config-guide.md)。

## CLI 参考（65+ 命令）

### 契约层

```bash
spec-orch discuss                     # 交互式头脑风暴 TUI
spec-orch mission create "标题"        # 创建 mission + spec 骨架
spec-orch mission approve <id>        # 冻结 spec
spec-orch mission status              # 列出所有 mission
spec-orch contract generate <id>      # 从 issue 生成 TaskContract
```

### 任务层

```bash
spec-orch plan <mission-id>           # LLM scoper 生成 DAG
spec-orch plan-show <mission-id>      # 查看波次/包分解
spec-orch promote <mission-id>        # 从计划创建 Linear issues
spec-orch pipeline <mission-id>       # 显示 EODF 流水线进度
```

### 执行层

```bash
spec-orch run <id> --source linear    # 完整一次性流水线
spec-orch run-plan <mission-id>       # 并行波次执行计划
spec-orch run-issue <id>              # 构建 + 验证 + 门控
spec-orch daemon start                # 自主 daemon 模式
```

### 证据层

```bash
spec-orch gate evaluate <id>          # 评估门控条件
spec-orch review-issue <id>           # 带判定的审查
spec-orch accept-issue <id>           # 人工验收
spec-orch explain <id>                # 门控解释报告
spec-orch retro <mission-id>          # Mission 复盘
```

### 控制层

```bash
spec-orch status <id>                 # 当前运行状态
spec-orch status --all                # 所有 issue 表格
spec-orch dashboard                   # Web 仪表盘
spec-orch watch <id>                  # 实时活动日志
spec-orch config check                # 验证配置
```

### 进化层

```bash
spec-orch evidence summary            # 模式分析
spec-orch harness synthesize          # 自动生成规则
spec-orch prompt evolve               # A/B 测试 prompt
spec-orch strategy analyze            # Scoper 提示
spec-orch policy distill              # 零 LLM 脚本
```

## 文档

### 愿景与架构

- [Project Vision](VISION.md) / [项目愿景](VISION.zh.md)
- [Seven Planes 架构映射](docs/architecture/seven-planes.md)
- [Roadmap v2](docs/plans/2026-03-roadmap-v2.md)

### 设计（当前）

- [自进化架构](docs/specs/self-evolution/spec.md)
- [流水线角色与阶段](docs/architecture/pipeline-roles-and-stages.md)
- [编排大脑设计](docs/architecture/orchestration-brain-design.md)
- [上下文契约设计](docs/architecture/context-contract-design.md)
- [Spec-Contract 集成](docs/architecture/spec-contract-integration.md)
- [变更管理策略](docs/architecture/change-management-policy.md)
- [SDD 行业定位](docs/architecture/sdd-landscape-and-positioning.md)

### 参考与指南

- [spec-orch.toml 参考](docs/reference/spec-orch-toml.md)
- [AI 配置指南](docs/guides/ai-config-guide.md)
- [EODF + ACPX 指南](docs/guides/eodf-acpx-guide.md)

### 历史（决策记录）

- [系统设计 v0](docs/architecture/spec-orch-system-design-v0.md)
- [V1 实施计划](docs/plans/2026-03-07-spec-orch-v1-implementation.md)

## 许可

本项目基于 MIT 许可证。详见 [LICENSE](LICENSE)。
