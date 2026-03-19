# SpecOrch 全局状态盘点与后续路线图

> 日期: 2026-03-18
> 基于: Linear issue 全量审计 + 代码/文档交叉验证
> 前置: [竞品分析路线图](2026-03-10-competitive-analysis-and-roadmap.md)

---

## 0.1 CEO 正式规划基线（2026-03-19 补充）

为避免后续方向漂移，后续执行统一以以下文档为准：

- `~/.gstack/projects/fakechris-spec-orch/ceo-plans/2026-03-19-credibility-flywheel.md`

执行口径更新为：

- 主线范围：P0 / P1 / P2 / P5 / P6
- P4 仅保留 Skill Format Definition（不进入 Full Runtime）
- 明确延后：Preview abstraction、Sandbox abstraction、Full Skill Runtime
- 运行模式：`SELECTIVE_EXPANSION`
- 节奏约束：先完成 P0 Context Contract（`SON-174`, `SON-177~180`），再推进飞轮后续阶段
- 思维模型：P0 -> P1 -> P6 为持续闭环，不是一次性串行阶段

---

## 一、Linear 清理结果

### 1.1 本次清理统计

| 操作 | 数量 | 涉及 issue |
|------|------|-----------|
| Backlog → Done | 30 | SON-37/41/48-51/97-105/107-114/126-132/134 |
| Backlog → Canceled | 7 | SON-53-55/57-60/62-66/124 (含历史 Canceled) |
| Done → Done (已正确) | 60+ | 所有已标记 Done 的 issue 确认无误 |

### 1.2 清理后残余 Backlog

| Issue | 标题 | 类型 | 评估 |
|-------|------|------|------|
| SON-44 | Daemon & 持续运行 | Epic | 大部分子 issue 已 Done，仅 SON-46 待做 |
| SON-46 | Daemon 健壮性: 重启恢复 + 错误重试 + 死信队列 | 子 issue | 真实 Backlog |
| SON-68 | AI-Assisted Conflict Resolution | Epic | 真实 Backlog，优先级中 |
| SON-72 | Daemon Hotfix Mode | Epic | 真实 Backlog，优先级中 |

---

## 二、已完成能力盘点

### 12 个 Phase / Epic 全部完成

| Phase | Epic | 核心交付 | PR |
|-------|------|---------|-----|
| 0-5 | SON-37/41/44/48 | Gate-as-a-Layer、EODF 闭环、Daemon、开发者体验 | #1-#30 |
| 6 | SON-74 | Self-Evolution: 6 个 Evolver + EvidenceAnalyzer | #31-#38 |
| 7 | SON-83 | Mission Control Center: EventBus、Lifecycle、TUI | #39-#42 |
| 8 | SON-100 | 混合架构: 三层分离 + Spec 发现路径 | #43-#48 |
| 9 | SON-106 | 编排大脑: FlowEngine + Conductor + 进化肌肉 | #43-#48 |
| 10 | SON-115 | 可插拔适配器: 4 Builder + 2 Reviewer | #50 |
| 11 | SON-122 | E2E 验证: OpenCode + MiniMax 闭环 | #51-#52 |
| 12 | SON-123 | 上下文治理: ContextBundle + ArtifactManifest + EvolutionTrigger | #56-#60 |

### 当前系统能力一览

```
spec-orch 当前能力矩阵:

[✅] 多流程骨架        Full / Standard / Hotfix + 升降级
[✅] 可插拔执行器      Codex / OpenCode / Claude Code / Droid
[✅] 可插拔审查器      Local / LLM (litellm)
[✅] 8 条件 Gate       spec_exists → human_acceptance
[✅] Agent 行为合约    compliance.contracts.yaml + regex 检测
[✅] 四层 Memory       Working / Episodic / Semantic / Procedural
[✅] 6 个 Evolver      Prompt / Plan / Harness / Policy / Intent / FlowPolicy
[✅] 进化触发器        config-driven, spec-orch.toml [evolution]
[✅] 上下文基础设施    ContextBundle / ContextAssembler / ArtifactManifest
[✅] 结构化 Builder    envelope 渲染 (acceptance criteria + spec + constraints)
[✅] Linear 集成       Issue 拉取 + 状态回写 + Comment
[✅] GitHub 集成       PR 创建 + Review webhook
[✅] Daemon 模式       Linear 轮询 + Mission 级执行
[✅] TUI               React/Ink terminal interface
[✅] Dashboard         WebSocket 实时推送 + 操作按钮
[✅] OpenSpec 流程     proposal → spec → design → tasks → contract
```

---

## 三、Gap 分析：已建未连 vs 真正缺失

### 3.1 已建基础设施但尚未全面接入的

| 基础设施 | 当前接入节点 | 未接入节点 | 影响 |
|----------|------------|-----------|------|
| ContextAssembler | Builder (envelope), LLMReview (extra context) | ReadinessChecker, Planner, Scoper, IntentClassifier | 4 个执行节点仍用 ad-hoc prompt |
| ArtifactManifest | RunController._finalize_run | Evolvers, ContextAssembler.assemble | 生成了 manifest 但下游未消费 |
| EvolutionTrigger | 代码实现完成 | 未接入 RunController 主流程 | 进化仅手动触发 |
| ContextBundle 数据类 | 定义完成 | 仅 ContextAssembler 内部使用 | 节点间未用 ContextBundle 传递 |

### 3.2 真正缺失的能力

| 缺失 | 对应文档/Issue | 重要性 |
|------|--------------|--------|
| Daemon 健壮性 (重启恢复/重试/死信) | SON-46 | 生产可用前提 |
| Contract 自动生成 | spec-contract-integration.md Phase 2 | 减少人工，提升 agent 安全性 |
| AI Conflict Resolution | SON-68 | Daemon 无人值守的前提 |
| Daemon Hotfix Mode | SON-72 | 紧急场景支持 |
| Daemon + MiniMax 实测 | 路线图 Phase 11 🔲 | 低成本自动化验证 |
| Gate 通过 → 自动 PR → 自动 merge | 路线图 Phase 11 🔲 | 真正的无人值守闭环 |
| ContextAssembler 全面接入 | context-contract-design.md 延伸 | 消除 ad-hoc prompt |

---

## 四、后续路线图

### Phase 13: 上下文全面接入 + 进化闭环落地

**目标**: 把 Phase 12 建好的基础设施真正接入所有 LLM 节点，实现"可装配上下文"的
承诺。同时让 EvolutionTrigger 自动触发，而非手动。

| 编号 | 任务 | 优先级 | 预估 |
|------|------|--------|------|
| 13-1 | ContextAssembler 接入 ReadinessChecker | P0 | 0.5d |
| 13-2 | ContextAssembler 接入 Planner (plan + answer_questions) | P0 | 1d |
| 13-3 | ContextAssembler 接入 Scoper | P0 | 0.5d |
| 13-4 | ContextAssembler 接入 IntentClassifier / Conductor | P0 | 0.5d |
| 13-5 | ArtifactManifest 消费：Evolvers 通过 manifest 定位原始制品 | P0 | 1d |
| 13-6 | EvolutionTrigger 接入 RunController._finalize_run | P0 | 0.5d |
| 13-7 | Daemon + MiniMax 全链路实测 (daemon 模式 + 自动执行) | P1 | 1d |
| 13-8 | Gate 通过 → 自动 PR → 自动 merge 端到端验证 | P1 | 1d |

**验收标准**:
- 所有 12 个 LLM 节点通过 ContextAssembler 获取上下文
- EvolutionTrigger 在每 N 次 run 后自动触发
- Daemon 模式下 MiniMax 实测成功记录

### Phase 14: 生产健壮性

**目标**: 让 Daemon 具备生产环境所需的健壮性，支持紧急场景。

| 编号 | 任务 | Linear | 优先级 |
|------|------|--------|--------|
| 14-1 | Daemon 重启恢复: 持久化进行中 issue 状态 | SON-46 | P0 |
| 14-2 | 错误重试策略: 指数退避 + 最大重试次数 | SON-46 | P0 |
| 14-3 | 死信队列: 多次失败的 issue 移入 dead letter | SON-46 | P1 |
| 14-4 | Daemon Hotfix Mode: 跳过 triage + 最小 gate | SON-72 | P1 |
| 14-5 | AI Conflict Resolution: Builder 自动解决 merge conflict | SON-68 | P2 |

**验收标准**:
- Daemon 重启后恢复之前的执行状态
- 失败 issue 在 N 次重试后进入 dead letter
- Hotfix 流程从 issue 到 merge < 5 分钟

### Phase 15: Contract 自动化 + Spec 增强

**目标**: 实现 spec-contract-integration.md 中的 Phase 2/3，让 Conductor
能自动为高风险 task 生成 Contract。

| 编号 | 任务 | 优先级 |
|------|------|--------|
| 15-1 | Contract 模板标准化 (基于 openspec/ 积累的 10+ 样本) | P0 |
| 15-2 | `generate-task-contract` Conductor Skill 实现 | P0 |
| 15-3 | Risk Level 自动评估 (import graph + 修改文件被引用次数) | P1 |
| 15-4 | Gate 增加 contract_violations 检查维度 | P1 |
| 15-5 | ContractEvolver: 从越界事件学习改进 contract 生成 | P2 |

### Phase 16: 产品化与发布准备

**目标**: 从原型走向可发布产品。

| 编号 | 任务 | 优先级 |
|------|------|--------|
| 16-1 | TUI 集成测试 + 稳定性验证 | P1 |
| 16-2 | 文档刷新: 快速上手指南 + API 文档 | P1 |
| 16-3 | PyPI 发布流程自动化 | P2 |
| 16-4 | Mission Control Center 集成测试 (SON-83 遗留) | P1 |
| 16-5 | 端到端 dogfood: 用 spec-orch 开发 spec-orch 连续 7 天 | P0 |

---

## 五、建议执行顺序

```
Phase 13 (上下文全面接入)     ← 当前最高优先级，完成 SON-123 的"最后一公里"
    ↓
Phase 14 (生产健壮性)         ← Daemon 可靠性，无人值守前提
    ↓
Phase 15 (Contract 自动化)    ← 提升 agent 安全性和执行质量
    ↓
Phase 16 (产品化)             ← 对外发布准备
```

**Phase 13 是当前推荐的下一步**，理由：
1. Phase 12 (SON-123) 建好了 ContextBundle/Assembler/Manifest 基础设施，但只接入了
   Builder 和 Review 两个节点，还有 4 个执行节点和全部进化节点未接入
2. EvolutionTrigger 代码已写好但未接入主流程，进化是系统核心差异化
3. 这些是"连线"工作，代码改动量不大但系统收益显著

---

## 六、与设计文档的对照检查

| 设计文档 | 当前实现状态 | 未覆盖项 |
|----------|------------|---------|
| orchestration-brain-design.md | 三流程骨架 ✅, 6 Evolver ✅, 升降级 ✅ | Memory→Evolution 数据管道的深度连接 |
| context-contract-design.md | Phase 0-3 基础设施 ✅ | ContextAssembler 全面接入 (Phase 13) |
| evolution-trigger-architecture.md | Config-driven trigger ✅ | Trigger 未接入 RunController 主流程 |
| spec-contract-integration.md | 手动 contract ✅ (T3.3 实验) | 自动生成 (Phase 15) |
| skill-driven-vs-spec-driven.md | 混合取舍已确认 ✅ | Skill 化的深入 (长期) |
| sdd-landscape-and-positioning.md | 行业定位确认 ✅ | — |

---

## 七、总结

spec-orch 已经完成了从"原型"到"功能完备的编排系统"的跨越。12 个 Phase/Epic
全部完成，覆盖了核心管线、可插拔适配器、自进化体系、上下文治理等关键能力。

**当前处于"基础设施完备、全面接入待做"的阶段。** 最有价值的下一步是 Phase 13：
把已建好的 ContextAssembler、ArtifactManifest、EvolutionTrigger 真正接入所有
LLM 节点和主流程，让系统从"部分结构化"跃迁到"全面结构化"。
