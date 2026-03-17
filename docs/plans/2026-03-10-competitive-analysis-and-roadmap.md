# SpecOrch 竞品分析与发展路线图

> 日期: 2026-03-10
> 基于: 工程审查 + 竞品对比分析
> 输入: Cyrus (ceedaragents/cyrus), cc-connect (chenhg5/cc-connect), Remodex (Emanuele-web04/remodex)

---

## 一、竞品全景

### 1.1 定位对比

| 维度 | SpecOrch | Cyrus | cc-connect | Remodex |
|------|----------|-------|------------|---------|
| **核心定位** | 自进化交付编排 + Gate 层 + 闭环改进 | Issue-driven agent 执行器 | Agent ↔ 消息平台桥接 | Codex 移动端遥控 |
| **语言** | Python 3.13 | TypeScript (monorepo) | Go | Swift + JS |
| **Stars** | — | 411 | 756 | 199 |
| **成熟度** | 原型 (29 commits) | 生产级 (1,127 commits, 25 releases) | 生产级 (226 commits, 17 releases) | 早期 (17 commits) |
| **Issue 来源** | 本地 fixture (Linear 计划中) | Linear + GitHub (实际运行) | 无 (消息驱动) | 无 |
| **Agent 支持** | Codex + OpenCode + Claude Code + Droid (可插拔) | Claude Code + Codex + Cursor + Gemini | 7 种 agent | Codex |
| **Codex 集成方式** | `codex app-server` JSON-RPC 手写客户端 | `codex exec --json` | `codex exec --json` | `codex app-server` WebSocket |
| **工作区隔离** | git worktree | git worktree | 无 (项目目录) | 无 |
| **Gate / 门禁** | ✅ 结构化 8 条件门禁 | ❌ 无 | ❌ 无 | ❌ 无 |
| **Builder 合规检测** | ✅ pre-action narration 检测 | ❌ 无 | ❌ 无 | ❌ 无 |
| **审计链路** | ✅ explain.md + report.json + events.jsonl | 部分 (Linear comment 流) | 无 | 无 |
| **Daemon 模式** | ✅ daemon + systemd/launchd | ✅ 持久进程 | ✅ daemon + systemd | ❌ 无 |
| **回写** | ❌ 本地制品 | ✅ Linear comment + PR | ✅ 消息平台 | ✅ Codex.app 刷新 |
| **商业模式** | 无 | Pro/Team/Community 分层 | 开源 (MIT) | TestFlight → 付费 App |

### 1.2 Codex 集成方式的市场共识

这是最关键的竞品发现。三个项目中有两个（Cyrus、cc-connect）使用 `codex exec --json`，只有 Remodex 使用 `app-server` JSON-RPC（因为它需要交互式 UI 控制）。

| 项目 | 集成方式 | 代码量 | 原因 |
|------|---------|-------|------|
| Cyrus | `codex exec --json` | ~200 行 (CodexRunner + session) | 自动化，无需交互 |
| cc-connect | `codex exec --json` | ~300 行 (codex.go + session.go) | 自动化，无需交互 |
| Remodex | `codex app-server` stdio/WebSocket | ~1000 行 (bridge) | 需要 iPhone 实时交互控制 |
| **SpecOrch** | `codex app-server` stdio JSON-RPC | **941 行** | 自动化，不需要交互 |

**结论**: SpecOrch 的使用场景是自动化编排，不需要交互式控制。`codex exec --json` 是正确选择。当前 941 行的 app-server 客户端是不必要的复杂度。

### 1.3 Cyrus 深度对比（最直接竞品）

**Cyrus 已经拥有的能力：**
- Linear webhook 接收 → issue 路由 → worktree 创建 → agent 执行 → Linear comment 回写
- 多 agent 支持（4 种 CLI runner）
- 子程序（subroutine）流程：coding → verifications → git-gh → summary
- Label 驱动的 AI 模式路由（debugger/builder/scoper）
- 用户权限控制
- MCP 集成
- 中途提示（mid-implementation prompting）
- Edge-proxy 分布式架构

**Cyrus 不具备的能力（SpecOrch 的差异化空间）：**
1. **结构化 Gate 层** — Cyrus 没有机器强制的合并门禁。它的验证只是一个 subroutine 步骤，不是独立的判定层。
2. **Builder 合约合规检测** — Cyrus 不检测 agent 是否在首个 action 前产生无效叙述。
3. **结构化审计制品** — Cyrus 的审计是 Linear comment 流，不是结构化的 `report.json` + `explain.md`。
4. **多条件门禁** — SpecOrch 的 8 条件 Gate（spec_exists, spec_approved, within_boundaries, builder, verification, review, preview, human_acceptance）比 Cyrus 的通过/不通过更细粒度。
5. **独立的 Review 层** — Cyrus 没有将 review 作为独立的管线阶段。

### 1.4 cc-connect 启示

cc-connect 虽然不是编排系统，但其架构设计有几个值得借鉴的模式：

1. **`core.Agent` 接口** — 干净的 agent 适配器 Protocol：`Name()`, `StartSession()`, `Stop()`
2. **多 agent 并行** — 一个进程管理多个 agent 实例
3. **`codex exec --json` 的实现参考** — 其 Go 实现约 300 行，是 SpecOrch Python 重写的良好参考
4. **Daemon 模式** — systemd/launchd 集成

---

## 二、战略定位决策

### 2.1 SpecOrch 不应该做什么

| 不应做 | 原因 |
|--------|------|
| 试图成为另一个 Cyrus | Cyrus 在 issue→agent→feedback loop 上已有先发优势，1000+ commit 的领先不可能通过跟随赶上 |
| 试图成为消息平台桥接 | cc-connect 已覆盖 9 个平台，这不是 SpecOrch 的核心价值 |
| 重写 Codex app-server 客户端 | 市场共识是用 `codex exec`，维护手写 JSON-RPC 客户端没有回报 |
| 构建自己的 agent runtime | OpenAI Agents SDK、LangGraph 等已经存在 |

### 2.2 SpecOrch 应该聚焦什么

**核心差异化：Gate-as-a-Layer**

SpecOrch 的独特价值是没有任何竞品实现的**结构化合并门禁**。这应该成为产品核心：

1. **Gate 层**：机器强制的、多条件的、可审计的合并判定
2. **合规检测**：agent 行为合约的结构化检查（pre-action narration 只是第一个）
3. **审计链路**：每个 issue 的完整决策审计追踪
4. **Review 层**：独立于 builder 的结构化审查阶段

**辅助能力：编排管线**

管线本身（issue → workspace → build → verify → review → gate）是承载 Gate 层的基础设施，但不是目的本身。

### 2.3 集成策略

短期路径（3-4 周）：自给自足
- SpecOrch 自己完成从 Linear 拉取到本地执行的闭环
- 用 `codex exec` 作为 builder
- daemon 模式实现自动轮询

中期路径（1-3 个月）：开放 Gate 层
- 将 Gate 层设计为可被其他工具集成的组件
- 提供 `spec-orch gate evaluate --report report.json` 独立 CLI
- 考虑 Cyrus 插件/webhook 集成

---

## 三、整合路线图

以下路线图整合了工程审查的 findings 和竞品分析的战略洞察。

### Phase 0: 技术债清理（1 周）

**目标**: 消除工程审查中发现的结构性问题，为后续开发建立干净基线。

| 编号 | 任务 | 来源 | 优先级 |
|------|------|------|--------|
| P0-1 | 修复 README 中 fallback 描述与代码不一致 | Review H1 | 必须 |
| P0-2 | 提取 `_finalize_run()` 消除三处重复 | Review H2 | 必须 |
| P0-3 | 将 `default_turn_contract_compliance` 移到共享模块 | Review H4, M2 | 必须 |
| P0-4 | 定义 `BuilderAdapter(Protocol)` | Review H4, 竞品 cc-connect 启示 | 必须 |
| P0-5 | 定义 `IssueSource(Protocol)` | Review M1 | 必须 |
| P0-6 | 修改 `_load_fixture` 在 fixture 缺失时抛出错误 | Review M1 | 应做 |
| P0-7 | 添加 `ruff` + `mypy` 到开发依赖 | Review M6 | 应做 |
| P0-8 | 删除 `pi_builder_adapter.py` 废弃代码 | Review L1 | 可做 |
| P0-9 | 清理已合并的特性分支 | Review L2 | 可做 |

**验收标准**: 23 个测试继续全部通过，CLI 行为不变，代码通过 `ruff check` 和 `mypy`。

### Phase 1: Builder 重写 — `codex exec`（1 周）

**目标**: 用 `codex exec --experimental-json` 替换 941 行 app-server 客户端。这是竞品分析确认的**单次 ROI 最高的重构**。

| 编号 | 任务 | 说明 |
|------|------|------|
| P1-1 | 实现 `CodexExecBuilderAdapter` | 继承 `BuilderAdapter` Protocol，使用 `codex exec --experimental-json` |
| P1-2 | 保留遥测写入 | 从 JSONL stdout 事件流写入 `incoming_events.jsonl` |
| P1-3 | 保留 compliance 检测 | 对 `codex exec` 事件流执行相同的 pre-action narration 检查 |
| P1-4 | 保留 builder report 格式 | `builder_report.json` 格式不变 |
| P1-5 | 更新 RunController 使用新适配器 | 通过 `BuilderAdapter` Protocol 注入 |
| P1-6 | 归档 `codex_harness_builder_adapter.py` | 移到 `src/spec_orch/services/_archived/`，不删除 |
| P1-7 | 更新测试 | 更新集成测试中的 fake server 脚本 |

**预期效果**:
- 代码量从 941 行降到 ~150 行
- 从实验性 API 迁移到稳定 API
- 与 Cyrus 和 cc-connect 采用相同的集成架构

**验收标准**: 所有测试通过，`run-issue` 使用 `codex exec` 成功运行（需要本地安装 Codex CLI）。

### Phase 2: Linear Ingress（1-2 周）

**目标**: 实现 Linear issue 拉取，从 fixture 驱动转为真实 issue 驱动。

| 编号 | 任务 | 说明 |
|------|------|------|
| P2-1 | 添加 `httpx` 依赖 | Linear GraphQL API 客户端 |
| P2-2 | 实现 `LinearIssueSource` | 继承 `IssueSource` Protocol |
| P2-3 | Linear issue → `Issue` model 映射 | title, description, labels, assignee |
| P2-4 | 添加 `--source linear\|fixture` CLI flag | 显式选择 issue 来源 |
| P2-5 | 环境变量配置 | `SPEC_ORCH_LINEAR_TOKEN`, `SPEC_ORCH_LINEAR_TEAM_KEY` |
| P2-6 | Label 路由（可选） | 参考 Cyrus 的 `labelPrompts` 设计，根据 label 选择不同 builder 策略 |

**参考**: Cyrus 的 Linear 集成使用 OAuth + webhook，但 SpecOrch v1 可以先用 API token + polling，降低初始复杂度。

### Phase 3: Daemon 模式（1 周）

**目标**: 从 CLI 命令转为持久进程。这是"SpecOrch 成为真正编排器"的转折点。

| 编号 | 任务 | 说明 |
|------|------|------|
| P3-1 | 实现 `spec-orch daemon` 命令 | poll Linear → claim → run → record 循环 |
| P3-2 | per-issue lockfile | 防止重复执行同一 issue |
| P3-3 | 实现 `spec-orch rerun` | 按 issue ID 重跑 |
| P3-4 | 配置文件 `spec-orch.toml` | 替代散落的 CLI flags |
| P3-5 | 优雅关闭 | SIGINT/SIGTERM 处理 |

**参考**:
- cc-connect 的 daemon 模式 (`cc-connect daemon install/start/stop`)
- Cyrus 推荐 tmux/pm2/systemd 三种运行方式

### Phase 4: Gate 增强与独立化（2 周）

**目标**: 将 Gate 层从内嵌组件发展为可独立使用的判定引擎。这是 SpecOrch 的战略差异化。

| 编号 | 任务 | 说明 |
|------|------|------|
| P4-1 | Gate 配置化 | 可选的条件启用/禁用（不是所有项目都需要 8 个条件全开） |
| P4-2 | 自定义 Gate 条件 | 用户可定义自己的 gate 条件和检查逻辑 |
| P4-3 | `spec-orch gate evaluate` 独立 CLI | 输入 report.json，输出 verdict。可被 CI/CD 或其他工具调用 |
| P4-4 | Gate 策略文件 | `gate.policy.yaml` 定义哪些条件 block merge，哪些只是 warning |
| P4-5 | Compliance 框架泛化 | 将 pre-action narration 检测泛化为可配置的 agent 行为合约 |
| P4-6 | Compliance 报告 | 独立的 `compliance_report.json` 制品 |

**战略价值**: 这是 Cyrus、cc-connect、Remodex 都没有的能力。一个可配置的、结构化的合并门禁可以：
- 被 CI/CD 调用（GitHub Actions step）
- 被 Cyrus 等编排器集成为 post-execution gate
- 独立于具体 builder 使用

### Phase 5: Write-back 与闭环（1-2 周）

| 编号 | 任务 | 说明 |
|------|------|------|
| P5-1 | Linear comment write-back | 将 explain report 摘要写回 Linear issue comment |
| P5-2 | Linear state transition | Gate mergeable=true 时自动移动 issue 状态 |
| P5-3 | PR 创建 | 基于 worktree 分支创建 GitHub PR |
| P5-4 | PR status check | 将 Gate verdict 作为 GitHub PR check |

---

## 四、架构演进图

### 当前架构 (v0.1)

```
CLI command
  └── RunController (God Object, 570 行)
        ├── WorkspaceService → git worktree
        ├── ArtifactService → task.spec.md, progress.md, explain.md
        ├── CodexHarnessBuilderAdapter → codex app-server (941 行)
        ├── VerificationService → subprocess
        ├── LocalReviewAdapter → review_report.json
        ├── GateService → GateVerdict
        └── TelemetryService → events.jsonl
```

### 目标架构 (v1.0) → 当前实际架构

```
spec-orch daemon / CLI
  └── RunController
        ├── IssueSource (Protocol)               ← ✅ 已实现
        │     ├── FixtureIssueSource
        │     └── LinearIssueSource
        ├── WorkspaceService → git worktree       ← ✅ 已实现
        ├── ArtifactService → 制品写入             ← ✅ 已实现
        ├── BuilderAdapter (Protocol)             ← ✅ 可插拔
        │     ├── CodexExecBuilderAdapter
        │     ├── OpenCodeBuilderAdapter          ← ✅ (MiniMax 验证通过)
        │     ├── ClaudeCodeBuilderAdapter
        │     └── DroidBuilderAdapter
        ├── VerificationService → subprocess      ← ✅ 已实现
        ├── ReviewAdapter (Protocol)              ← ✅ 可插拔
        │     ├── LocalReviewAdapter
        │     └── LLMReviewAdapter (litellm)      ← ✅ (MiniMax 验证通过)
        ├── AdapterFactory                        ← ✅ spec-orch.toml 驱动
        ├── FlowEngine (骨架层)                    ← ✅ 已实现
        │     ├── Full / Standard / Hotfix 三流程
        │     ├── 流程升降级 + 回退
        │     └── IntentEvolver / FlowPolicyEvolver
        ├── ComplianceEngine → agent 行为合约检测   ← ✅ 已实现
        ├── GateService (可配置, 可独立调用)         ← ✅ 已实现
        │     ├── GatePolicy → gate.policy.yaml
        │     ├── GatePolicyEvolver
        │     └── GateVerdict + GateReport
        ├── TelemetryService → events.jsonl        ← ✅ 已实现
        └── WritebackService (Protocol)
              ├── LinearWriteback                   ← ✅ 已实现
              └── GitHubWriteback                   ← ✅ 已实现
```

关键演进：
1. `RunController` 从 God Object 变为薄协调层
2. 所有外部依赖通过 Protocol 注入
3. Gate 成为可独立使用的引擎
4. Compliance 从 builder 内嵌逻辑变为独立框架

---

## 五、执行节奏

| 阶段 | 时间 | 里程碑 | 状态 |
|------|------|--------|------|
| Phase 0 | 第 1 周 | 技术债清零，建立 ruff + mypy 基线 | ✅ 完成 |
| Phase 1 | 第 2 周 | `codex exec` builder 上线，941 行 → 150 行 | ✅ 完成 |
| Phase 2 | 第 3-4 周 | Linear issue 拉取工作 | ✅ 完成 |
| Phase 3 | 第 5 周 | daemon 模式，SpecOrch 成为持久服务 | ✅ 完成 |
| Phase 4 | 第 6-7 周 | Gate 独立化，compliance 框架 | ✅ 完成 |
| Phase 5 | 第 8-9 周 | Linear + GitHub write-back 闭环 | ✅ 完成 |
| **Phase 6** | **第 10 周** | **自进化：AutoHarness 闭环改进 (Epic SON-74, 8 issues)** | **✅ 完成** |
| **Phase 7** | **第 11-13 周** | **Mission Control Center (Epic SON-83)** | **🔄 集成测试待完成** |
| **Phase 8** | **第 14-16 周** | **混合架构: Talk Freely, Execute Strictly (Epic SON-100)** | **✅ 完成** |
| **Phase 9** | **第 17-20 周** | **编排大脑: 骨架确定性 + 肌肉智能化 (Epic SON-106)** | **✅ 完成** |
| **Phase 10** | **第 21 周** | **可插拔适配器架构 (Epic SON-115)** | **✅ 完成** |
| **Phase 11** | **第 22 周** | **端到端闭环验证: OpenCode + MiniMax (SON-122)** | **✅ CLI 验证通过** |

#### Phase 7: Mission Control Center (SON-83)

交互可视化与自主编排能力。

| 编号 | 任务 | 状态 |
|------|------|------|
| SON-84 | EventBus: pub/sub 事件总线 | ✅ |
| SON-85 | MissionLifecycleManager: Mission 级状态机 | ✅ |
| SON-86 | Daemon 接入 LifecycleManager | ✅ |
| SON-87 | Dashboard WebSocket 实时推送 + 操作按钮 | ✅ |
| SON-88 | Dashboard 多渠道 Discuss + Linear 增强 | ✅ |
| SON-89 | Evolution 看板可视化 | ✅ |
| SON-90 | Memory 子系统 (MemoryProvider + FileSystem + Migration) | ✅ |
| SON-91 | Rich TUI: TypeScript + React/Ink | ✅ |
| SON-99 | Conductor Agent: Progressive Formalization Layer | ✅ |
| SON-83 | Epic 完成验收 + 集成测试 | 🔄 |

#### Phase 8: 混合架构 — "Talk Freely, Execute Strictly" (SON-100)

基于 SDD 行业分析（Spec Kit / Kiro / Tessl / agent-spec）和实战反思，将 spec-orch 定位为
**灵活交互 + 结构化执行 + 闭环进化**的三层架构。

| 编号 | 任务 | 状态 |
|------|------|------|
| SON-101 | Spec 模板库 | ✅ (Change 05, PR #47) |
| SON-102 | Conductor → DMA 全生命周期集成 | ✅ (Change 04, PR #46) |
| SON-103 | 流程检查 Skill 化 | ✅ (Change 06, PR #48) |
| SON-104 | 示例反推 Spec | ✅ (Change 05, PR #47) |
| SON-105 | 行业 Spec 格式兼容 | ✅ (Change 06, PR #48) |

#### Phase 9: 编排大脑 — 骨架确定性 + 肌肉智能化 (SON-106)

基于学术研究（SEW / MetaAgent / Live-SWE-agent / VIGIL）和实战反思，实现两层分离的编排大脑：
骨架层（确定性流程拓扑）+ 肌肉层（LLM 驱动、可进化的节点逻辑）。

| 编号 | 任务 | 状态 |
|------|------|------|
| SON-107 | 骨架层: 三流程有向图 | ✅ (Change 01, PR #43) |
| SON-108 | 流程升降级 | ✅ (Change 01, PR #43) |
| SON-109 | Intent → Flow Mapping | ✅ (Change 01, PR #43) |
| SON-110 | Conductor Fork | ✅ (Change 02, PR #44) |
| SON-111 | IntentEvolver | ✅ (Change 03, PR #45) |
| SON-112 | FlowPolicyEvolver | ✅ (Change 03, PR #45) |
| SON-113 | GatePolicyEvolver | ✅ (Change 03, PR #45) |
| SON-114 | Memory → Evolution 数据管道 | ✅ (Change 03, PR #45) |

设计参考: `docs/architecture/orchestration-brain-design.md`

#### Phase 10: 可插拔适配器架构 (SON-115)

将 Builder、Reviewer 等核心模块改造为可插拔、可配置的架构，支持多种 Coding CLI 作为执行器，
降低闭环运行成本（MiniMax 无限 token 替代 Codex）。

| 编号 | 任务 | 状态 |
|------|------|------|
| SON-116 | ReviewAdapter Protocol + adapter_factory + 注入改造 | ✅ (PR #50) |
| SON-117 | OpenCode Builder Adapter | ✅ (PR #50) |
| SON-118 | Droid Builder Adapter | ✅ (PR #50) |
| SON-119 | Claude Code Builder Adapter | ✅ (PR #50) |
| SON-120 | LLM Review Adapter | ✅ (PR #50) |
| SON-121 | 端到端闭环验证 | ✅ (PR #50) |

配置方式: `spec-orch.toml` 的 `[builder]` 和 `[reviewer]` 段。

#### Phase 11: 端到端闭环验证 — OpenCode + MiniMax (SON-122)

首次使用低成本替代模型完成完整管线执行，验证可插拔架构的真实可用性。

| 编号 | 任务 | 状态 |
|------|------|------|
| SON-122 | acpx 调研 — 作为 E2E 验证用例 | ✅ (PR #51, #52) |
| — | CLI 单 issue 闭环: `run-issue SON-122 --source linear --live` | ✅ 验证通过 |
| — | OpenCode builder (MiniMax-M2.5 模型) 执行成功 | ✅ ~2.5min, $0.043 |
| — | LLM reviewer (MiniMax via litellm OpenAI-compat) 执行成功 | ✅ verdict=uncertain |
| — | Gate 正确 BLOCKED (verification/review/human_acceptance) | ✅ 符合预期 |
| — | Builder CWD worktree 逃逸修复 | ✅ (PR #52) |
| — | builder_report.json 覆盖修复 | ✅ (PR #52) |
| — | Daemon 轮询模式 + MiniMax 实测 | 🔲 代码支持，未实测 |

**闭环跑通范围：**
- ✅ **CLI 单次执行**: `spec-orch run-issue <ID> --source linear --live`，从 Linear 拉取 issue → OpenCode builder (MiniMax) 构建 → 验证 → LLM review (MiniMax) → Gate 判定，全链路执行完毕
- ✅ **低成本模型验证**: MiniMax-M2.5 无限 token 替代 Codex/Claude，单次执行成本 ~$0.04
- ✅ **多 adapter 切换**: 通过 `spec-orch.toml` 的 `[builder]` / `[reviewer]` 段即可切换 builder 和 reviewer，无需改代码
- 🔲 **Daemon 轮询**: `daemon.py` 已使用 `adapter_factory`，代码层面支持 OpenCode，但尚未以 Daemon 模式实际运行过 MiniMax 闭环
- 🔲 **Gate 通过 → 自动 PR → 自动 merge**: SON-122 为纯文档调研任务，Gate 因 typecheck/test 失败而正确 BLOCKED，完整自动合并路径待后续功能 issue 验证

**发现的问题及修复 (PR #52):**
1. Builder prompt 缺少 CWD 约束 → 文件写入主仓库而非 worktree → 在所有 adapter PREAMBLE 中添加 CWD 指令
2. 测试中 `_PassingBuilderAdapter` 使用相对路径 → pytest 覆盖 builder_report.json → 规范化为 workspace 绝对路径
3. Integration test blocked_by 顺序不稳定 → 改为灵活断言

每个 Phase 结束时的检查点：
- 所有测试通过
- `ruff check` + `mypy` 无新增错误
- README 与代码行为一致
- 至少有一个完整的端到端 dogfood 运行记录

---

## 六、关键决策记录

| 决策 | 理由 | 替代方案 | 为何不选 |
|------|------|---------|---------|
| 用 `codex exec` 替换 `app-server` | 市场共识（Cyrus + cc-connect）、稳定 API、减少 800 行代码 | 继续维护 app-server 客户端 | 协议实验性、维护成本高、无交互需求 |
| Gate 层作为核心差异化 | 唯一没有竞品覆盖的能力 | 全面追赶 Cyrus 的 Linear 集成 | 先发优势无法弥补 |
| 先 daemon 后 write-back | daemon 是"真正编排器"的前提；有了 daemon，write-back 才有真实使用场景 | 先 write-back | write-back 没有 daemon 支撑只是一次性脚本 |
| 不做消息平台桥接 | cc-connect 已覆盖 9 个平台，这不是 SpecOrch 的价值 | 添加 Slack/Discord 集成 | 市场已有成熟方案 |
| Protocol 抽象优先于功能新增 | 当前 God Object 结构会让每个新功能的开发成本递增 | 直接开发 Linear 集成 | 在 God Object 上堆叠功能会加速技术债 |
| **混合架构取代纯 Spec-Driven** | 实战暴露纯 pipeline 的僵化问题；SDD 行业趋势验证灵活交互的必要性 | 继续硬编码 pipeline | 流程变化需改代码，DMA 无法动态分流 |
| **不自创 spec 格式** | Spec Kit (76K stars) / Kiro / Tessl 已有行业标准 | 自定义 spec DSL | 重复造轮子，降低互操作性 |

---

## 七、风险与不确定性

| 风险 | 影响 | 缓解 |
|------|------|------|
| `codex exec --experimental-json` 仍标记为 experimental | 格式可能变更 | 参考 Cyrus/cc-connect 的实现，它们在生产中使用此接口；保持薄适配层 |
| Linear API 变更 | 破坏 ingress | 使用官方 Python SDK 而非裸 httpx（如果存在质量可接受的 SDK） |
| Gate 独立化的需求是否真实 | 投入可能无回报 | Phase 4 前先在社区验证需求（如 HN 讨论） |
| Cyrus 可能后续也实现 Gate 层 | 差异化被消除 | 尽早建立 Gate 层的深度和配置能力，形成技术护城河 |

---

## 八、与现有 Review 文档的关系

本文档建立在 `docs/reviews/2026-03-08-spec-orch-review.md` 的分析基础上，但补充了：
1. 三个竞品项目的实际代码级对比（非表面 README 对比）
2. Codex 集成方式的市场共识验证
3. 基于竞争格局的战略定位决策
4. 整合工程审查 findings 和竞品洞察的优先级排序

现有 review 文档中的建议（IssueSource 提取、BuilderAdapter Protocol、`codex exec` 重写、`_finalize_run` 提取）全部被保留并排入本路线图的 Phase 0-1。
