# Seven Planes 架构映射

本文将 spec-orch 的代码库按七层架构（Seven Planes）进行映射，标注每个平面的已实现模块、
缺失部分、下一步优先级，以及从竞品（Capy / Fabro / Lody / Composio / Thariq / LangChain）
吸收的设计思路。

> 参见 [VISION.md](../../VISION.md) 了解七层架构的完整定义。

---

## 概览

```
┌─────────────────────────────────────────────────────┐
│  G. Evolution Plane                                 │
│     traces → evals → prompt/policy/harness 进化     │
├─────────────────────────────────────────────────────┤
│  F. Control Plane                                   │
│     mission / session / PR / gate / 运营控制塔       │
├─────────────────────────────────────────────────────┤
│  E. Evidence Plane                                  │
│     findings / tests / preview / gate / deviation   │
├─────────────────────────────────────────────────────┤
│  D. Execution Plane                                 │
│     worktree / sandbox / session / agent adapter    │
├─────────────────────────────────────────────────────┤
│  C. Harness Plane                                   │
│     context contract / skills / policies / hooks    │
├─────────────────────────────────────────────────────┤
│  B. Task Plane                                      │
│     plan DAG / wave / work packet / 依赖 / 广播     │
├─────────────────────────────────────────────────────┤
│  A. Contract Plane                                  │
│     spec / scope / acceptance / decisions / freeze  │
└─────────────────────────────────────────────────────┘
```

---

## A. Contract Plane — 契约平面

**职责**：把意图冻结成机器可执行的约束。Spec 是唯一真相。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| Mission 模型 | `domain/models.py` | Mission / Spec 生命周期管理 |
| Spec 冻结 | `cli.py` → `mission approve` | `@freeze` + approve 命令 |
| Spec 快照 | `services/spec_snapshot_service.py` | 版本化 spec 快照 |
| Spec 生成器 | `services/spec_generator.py` | 从 plan → fixture JSON |
| Spec 导入 | `spec_import/` | BDD / EARS / SpecKit 格式导入 |
| 任务契约 | `domain/task_contract.py` | TaskContract 结构化约束 |
| Conductor | `services/conductor/` | 渐进形式化：intent → crystallize → approve |
| 讨论层 | `services/conversation_service.py` | TUI / Linear / Slack 多通道讨论 |

### 缺失 / 待补

- Spec 版本对比与 diff 可视化
- Spec 变更影响分析（哪些 task 需要重跑）

### 竞品吸收

- **Capy**: Captain 只读代码、写 task spec，不改文件。spec-orch 的 Conductor 已有同等精神，
  下一步是让这个分工更显式、更可配置。

---

## B. Task Plane — 任务平面

**职责**：将 spec 展开成可并行、可依赖、可广播的任务图。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| ExecutionPlan / Wave / WorkPacket | `domain/models.py` | DAG 数据结构 |
| Scoper | `services/scoper_adapter.py` | LLM 拆解 spec → 波次计划 |
| Plan 解析 | `services/plan_parser.py` | Markdown plan → 结构化 DAG |
| Promotion | `services/promotion_service.py` | WorkPacket → Linear Issues |
| 波次执行 | `services/wave_executor.py` | 波次内并行 |
| 并行控制器 | `services/parallel_run_controller.py` | 多波次并行调度 |
| Packet 执行 | `services/packet_executor.py` | 单工作包全流水线 |

### 缺失 / 待补

- 持久化 Task Graph（当前 DAG 是内存中的一次性对象）
- 任务级依赖阻塞与自动解阻
- 跨 session / 跨 subagent 的任务协作
- 任务图可视化（DOT / Mermaid 输出）

### 竞品吸收

- **Claude Code Tasks**: 任务不是 todo，而是持久化 task graph，带依赖、阻塞、owner、关联 evidence。
- **Composio agent-orchestrator**: 每个 agent 一个 worktree + branch + PR，CI fail 自修，
  review 自回。spec-orch 已有 worktree 隔离，下一步是把 reaction 做成一等对象。

---

## C. Harness Plane — 装配平面

**职责**：让执行变稳定——不是靠运气，而是靠系统轨道。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| ContextAssembler | `services/context_assembler.py` | 结构化上下文装配 |
| ContextBundle | `domain/context.py` | TaskContext / ExecutionContext / LearningContext |
| 流程图 | `flow_engine/` | Full / Standard / Hotfix 流程骨架 |
| 流程策略 | `flow_engine/mapper.py` | 流程选择 + 升降级 |
| 合规引擎 | `services/compliance_engine.py` | YAML 定义的 agent 行为约束 |
| Gate Policy | `gate.policy.yaml` | 可配置门控条件和 profile |
| Adapter Factory | `services/adapter_factory.py` | 从 TOML 配置动态实例化 |
| 项目探测 | `services/project_detector.py` | `spec-orch init` 自动检测项目类型 |
| 验证命令配置 | `spec-orch.toml` → `[verification]` | 可配置 lint/typecheck/test/build |

### 缺失 / 待补

- Cache-safe prompt layout（静态前缀稳定化 + cache hit rate 监控）
- Skill 加载与 progressive disclosure
- Repo-level hooks / setup / preview / tool policies
- Reaction engine（CI fail → 自动修复、review change → 自动回应）
- Sandbox provider abstraction
- 回退策略（fallback）和重试规则

### 竞品吸收

- **Thariq / Claude Code**: Prompt Caching Is Everything — 按 prefix caching 设计 harness 顺序：
  static first, dynamic last。cache hit rate 要像 uptime 一样被监控。
- **Thariq / Skills**: Skills 是新的 context 加载机制，强调 progressive disclosure、动态按需加载、
  可组合、可移植、可执行代码。
- **LangChain**: 从 52.8 → 66.5 (Terminal Bench 2.0)，模型不变，只改 harness。
  改进循环靠 traces 读失败模式。
- **Capy**: `.capy/settings.json` 定义 setup hooks、terminals、preview ports、tool hooks。
- **Composio**: `reactions` 配成一等对象（ci-failed / changes-requested / approved-and-green）。

---

## D. Execution Plane — 执行平面

**职责**：把每个工作包放进隔离环境里跑。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| Worktree 隔离 | `services/workspace_service.py` | 一任务一 worktree |
| RunController | `services/run_controller.py` | 主编排循环 |
| Codex Builder | `services/codex_exec_builder_adapter.py` | `codex exec --json` |
| OpenCode Builder | `services/opencode_builder_adapter.py` | OpenCode JSONL 事件流 |
| Claude Code Builder | `services/claude_code_builder_adapter.py` | Claude Code stream-json |
| Droid Builder | `services/droid_builder_adapter.py` | Factory Droid CLI |
| ACPX Builder | `services/acpx_builder_adapter.py` | 15+ agents 统一适配 |
| 验证服务 | `services/verification_service.py` | lint / typecheck / test / build |
| 冲突解决 | `services/conflict_resolver.py` | AI 辅助 merge conflict |
| Daemon | `services/daemon.py` | 自主轮询 + 构建 + 门控 |
| 取消处理 | `services/cancellation_handler.py` | 优雅取消机制 |

### 缺失 / 待补

- Container / VM sandbox（当前仅 worktree 隔离）
- Network allow/block list
- Snapshot / checkpoint / resume
- 执行超时与资源限制

### 竞品吸收

- **Lody**: 并行开发 = worktree 隔离，支持 session 回看、diff 审查、移动端推送。
- **Capy**: 每个 task 有独立 VM、branch、会话历史，可用不同模型跑同一任务。
- **Fabro**: sandbox provider abstraction、snapshot image、network policy。

---

## E. Evidence Plane — 证据平面

**职责**：用 review、preview、checks、gates 来证明完成。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| Gate Service | `services/gate_service.py` | 多条件门控评估 |
| Gate Skills | `services/gate_builtin_skills.py` | 内置门控技能 |
| Review Adapter | `services/review_adapter.py` / `llm_review_adapter.py` | 本地 + LLM 审查 |
| GitHub Review | `services/github_review_adapter.py` | GitHub PR 审查集成 |
| Deviation 跟踪 | `services/deviation_service.py` | spec 偏差记录 |
| Finding 管理 | `services/finding_store.py` | 结构化发现存储 |
| 活动日志 | `services/activity_logger.py` | 全过程活动记录 |
| Artifact 服务 | `services/artifact_service.py` | run artifact 管理 |
| 遥测 | `services/telemetry_service.py` | 运行数据收集 |

### 缺失 / 待补

- Preview 链接集成（Vercel / Netlify preview）
- 统一 run artifact schema（manifest / event stream / live snapshot / retro / conclusion）
- Structured review findings（类型 / 严重度 / 位置 / 增量 re-review）
- Acceptance lane（spec checklist + preview + findings + deviation + risk 汇聚到同一视图）
- 可查询的 run history（SQL / DuckDB analytics）

### 竞品吸收

- **Capy**: PR review 做到 summary 看能力而不是文件，findings 有类型/严重度/位置，
  re-review 增量。Preview + diff 并排。
- **Fabro**: `progress.jsonl` / `live.json` / `manifest.json` / `checkpoint.json` / `retro.json` /
  `conclusion.json`，支持 DuckDB 做跨 run SQL 分析。

---

## F. Control Plane — 控制平面

**职责**：给负责人一个真正能运营系统的控制塔。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| EventBus | `services/event_bus.py` | 发布/订阅事件总线 |
| Event 格式化 | `services/event_formatter.py` | 事件格式化输出 |
| Mission 管理 | `services/mission_service.py` | mission 生命周期 |
| Lifecycle 管理 | `services/lifecycle_manager.py` | 状态机 |
| GitHub PR | `services/github_pr_service.py` | PR 创建 / merge check / rebase |
| Linear 集成 | `services/linear_client.py` / `linear_write_back.py` | issue CRUD + 状态回写 |
| Dashboard | `dashboard.py` | Web 仪表盘 |
| TUI | `packages/tui/` | TypeScript + React/Ink 终端 UI |
| Daemon 安装 | `services/daemon_installer.py` | systemd / launchd |
| Pipeline 检查 | `services/pipeline_checker.py` | 流水线进度 11 阶段 |
| 配置检查 | `services/config_checker.py` | `spec-orch config check` |

### 缺失 / 待补

- Session-centric 视图（当前以 issue 为中心，缺少 session 维度）
- 成本 / cache-hit / token 消耗监控
- 卡住的 run 检测与告警
- 移动端通知与轻审批
- 团队多人协作视图
- Mission Control Center 升级（从"状态页"到"运营控制塔"）

### 竞品吸收

- **Lody**: session-centric 体验，worktree 管理，移动端推送，团队查看他人 session，
  对当前轮次和整场对话的 diff 审查。
- **Composio agent-orchestrator**: fleet dashboard，agent 状态、PR 生命周期一览。

---

## G. Evolution Plane — 进化平面

**职责**：让系统优化 harness，而不只是优化 prompt。

### 已实现

| 模块 | 文件 | 说明 |
|------|------|------|
| Evidence Analyzer | `services/evidence_analyzer.py` | 历史运行模式聚合 |
| Harness Synthesizer | `services/harness_synthesizer.py` | LLM 生成合规规则 + 回测 |
| Prompt Evolver | `services/prompt_evolver.py` | A/B 测试 + 自动晋升 |
| Plan Strategy Evolver | `services/plan_strategy_evolver.py` | 学习 scoper 提示 |
| Policy Distiller | `services/policy_distiller.py` | 高频任务蒸馏为零 LLM 脚本 |
| Intent Evolver | `services/intent_evolver.py` | 意图分类器进化 |
| Flow Policy Evolver | `services/flow_policy_evolver.py` | 流程策略进化 |
| Gate Policy Evolver | `services/gate_policy_evolver.py` | 门控策略进化 |
| Evolution Trigger | `services/evolution_trigger.py` | 配置驱动的进化生命周期 |
| Evolver Protocol | `services/evolver_protocol.py` | 进化器通用协议 |
| Memory | `services/memory/` | 跨 session 知识持久化 |

### 缺失 / 待补

- 统一 trace / run artifact schema（evolution 消费 artifacts 而非 anecdotes）
- Harness evals（固定模型 + 固定任务集 + 改 harness 变量 → 比较指标）
- Tool surface 进化（根据 trace 调整工具设计）
- Skill 层：介于 prompt 和 policy 之间的半结构化工作法
- 进化变更自动跑 eval，不只是看成功率摘要

### 竞品吸收

- **LangChain**: 性能跃迁往往来自 harness 而非换模型。改进循环：
  prompt → captured run (trace + artifacts) → checks → score。
- **Anthropic**: Skills 不是辅助 feature，而是新的 context/workflow primitive。
  支持组织级分发与跨产品复用。
- **OpenAI**: repo-local skills/AGENTS.md/scripts + evals。merged PR 数从 316 → 457。

---

## 文件索引速查

以下是每个 plane 对应的关键文件路径，方便开发者快速定位：

| Plane | 核心文件 |
|-------|---------|
| Contract | `domain/models.py`, `domain/task_contract.py`, `services/conductor/`, `services/spec_snapshot_service.py`, `spec_import/` |
| Task | `domain/models.py` (ExecutionPlan/Wave/WorkPacket), `services/plan_parser.py`, `services/promotion_service.py`, `services/wave_executor.py`, `services/parallel_run_controller.py` |
| Harness | `domain/context.py`, `services/context_assembler.py`, `services/adapter_factory.py`, `services/project_detector.py`, `flow_engine/`, `compliance.contracts.yaml`, `gate.policy.yaml` |
| Execution | `services/run_controller.py`, `services/workspace_service.py`, `services/*_builder_adapter.py`, `services/verification_service.py`, `services/daemon.py` |
| Evidence | `services/gate_service.py`, `services/deviation_service.py`, `services/finding_store.py`, `services/review_adapter.py`, `services/artifact_service.py` |
| Control | `cli.py`, `dashboard.py`, `services/event_bus.py`, `services/mission_service.py`, `services/lifecycle_manager.py`, `services/linear_client.py`, `services/github_pr_service.py` |
| Evolution | `services/evidence_analyzer.py`, `services/harness_synthesizer.py`, `services/prompt_evolver.py`, `services/policy_distiller.py`, `services/evolution_trigger.py`, `services/memory/` |
