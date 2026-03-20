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

## 0.2 文档层级与进度同步（2026-03-22）

**读文档顺序（战略 → 执行）：**

1. **[方向性深度拷问（2026-03-19）](../architecture/2026-03-19-directional-review.zh.md)** — 最新方向性结论、行动排序、**§6 未完成清单**（哪些战略条目尚未工程落地）。
2. **本文（2026-03-18）** — Phase 13~16、Gap、历史清理；其中 **Phase 13 主线已完成**，下文表格已更新。
3. **[上下文治理 / Context Contract（2026-03-17）](../architecture/context-contract-design.md)** — 12 节点与分 Phase 改造；**Phase 0~1 大体对齐 Phase 13 已落地**，Phase 2~3（进化深度）仍待推进。

**与「v0 系统设计」关系**：[`spec-orch-system-design-v0.md`](../architecture/spec-orch-system-design-v0.md) 为 **2026-03-07 历史文档**；口语中的「v0.6 / 方向性图谱」在 2026-03 语境下主要指 **上下文治理 + Phase 13** 这条线，**已被** `SON-174` / `SON-177~180`、统一 artifact 等 **大体覆盖**；未覆盖部分见方向性文档 §6.3 与本文 Phase 14+。

---

## 一、Linear 清理结果

### 1.1 本次清理统计

| 操作 | 数量 | 涉及 issue |
|------|------|-----------|
| Backlog → Done | 30 | SON-37/41/48-51/97-105/107-114/126-132/134 |
| Backlog → Canceled | 7 | SON-53-55/57-60/62-66/124 (含历史 Canceled) |
| Done → Done (已正确) | 60+ | 所有已标记 Done 的 issue 确认无误 |

### 1.2 清理后残余 Backlog

> **2026-03-20 更新**：以下 issue 已全部关闭为 Done（SON-44/46/68/72 + SON-162~166）。Linear 中当前无 open issue（170 Done / 16 Canceled）。

| Issue | 标题 | 类型 | 状态（2026-03-20） |
|-------|------|------|---------------------|
| SON-44 | Daemon & 持续运行 | Epic | ✅ Done |
| SON-46 | Daemon 健壮性: 重启恢复 + 错误重试 + 死信队列 | 子 issue | ✅ Done |
| SON-68 | AI-Assisted Conflict Resolution | Epic | ✅ Done |
| SON-72 | Daemon Hotfix Mode | Epic | ✅ Done |

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

> **2026-03-22 更新**：Phase 13 / `SON-177~180` 已把 **ReadinessChecker、Planner、Scoper、IntentClassifier、LLMReview、Evolver 侧 manifest 偏好** 等主线接入推进到「可交付」状态；下表保留为 **历史快照**，当前更准确的对照见 [方向性文档 §6](../architecture/2026-03-19-directional-review.zh.md)。

| 基础设施 | 当时缺口（2026-03-18） | 2026-03-22 说明 |
|----------|----------------------|----------------|
| ContextAssembler | 多节点未接入 | **主线节点已接入**；细节仍见各 adapter 渲染路径 |
| ArtifactManifest / `run_artifact` | 下游消费不全 | **统一 `run_artifact/*` + 兼容桥**已合入；Evolver/Reader 已偏好奇路径 |
| EvolutionTrigger | 未接入主流程 | **部分自动路径仍弱**；深度案例化见 [context-contract-design](../architecture/context-contract-design.md) Phase 2~3 |
| ContextBundle | 仅内部使用 | 已在接入节点通过 Assembler **结构化获取** |

### 3.2 真正缺失的能力

> **2026-03-22 更新**：SON-46/68/72 已完成；ContextAssembler 已全面接入。下表保留为历史快照。

| 缺失 | 对应文档/Issue | 重要性 | 状态（2026-03-22） |
|------|--------------|--------|---------------------|
| Daemon 健壮性 (重启恢复/重试/死信) | SON-46 | 生产可用前提 | ✅ Done |
| Contract 自动生成 | spec-contract-integration.md Phase 2 | 减少人工，提升 agent 安全性 | 🟡 Phase 15 待做 |
| AI Conflict Resolution | SON-68 | Daemon 无人值守的前提 | ✅ Done |
| Daemon Hotfix Mode | SON-72 | 紧急场景支持 | ✅ Done |
| Daemon + MiniMax 实测 | 路线图 Phase 11 🔲 | 低成本自动化验证 | ❌ 未做 |
| Gate 通过 → 自动 PR → 自动 merge | 路线图 Phase 11 🔲 | 真正的无人值守闭环 | 🟡 Reaction engine 基线有 |
| ContextAssembler 全面接入 | context-contract-design.md 延伸 | 消除 ad-hoc prompt | ✅ Phase 13 完成 |

---

## 四、后续路线图

### Phase 13: 上下文全面接入 + 进化闭环落地

**状态（2026-03-22）**: **主线已完成**（`SON-174`、`SON-177~180`、统一 artifact 等）。**13-7 / 13-8** 类验证仍属 **P1 产品/运维验证**，与 [方向性文档 §6.3 P1 外部 E2E](../architecture/2026-03-19-directional-review.zh.md) 一致，**未**随 Phase 13 代码主线一并关闭。

**目标**: 把 Phase 12 建好的基础设施真正接入所有 LLM 节点，实现"可装配上下文"的
承诺。同时让 EvolutionTrigger 自动触发，而非手动。

| 编号 | 任务 | 优先级 | 预估 | 状态（2026-03-22） |
|------|------|--------|------|-------------------|
| 13-1 | ContextAssembler 接入 ReadinessChecker | P0 | 0.5d | ✅ |
| 13-2 | ContextAssembler 接入 Planner (plan + answer_questions) | P0 | 1d | ✅ |
| 13-3 | ContextAssembler 接入 Scoper | P0 | 0.5d | ✅ |
| 13-4 | ContextAssembler 接入 IntentClassifier / Conductor | P0 | 0.5d | ✅ |
| 13-5 | ArtifactManifest 消费：Evolvers 通过 manifest 定位原始制品 | P0 | 1d | ✅（含 `run_artifact` 优先） |
| 13-6 | EvolutionTrigger 接入 RunController._finalize_run | P0 | 0.5d | 🟡 部分 / 深化见 context-contract Phase 2~3 |
| 13-7 | Daemon + MiniMax 全链路实测 (daemon 模式 + 自动执行) | P1 | 1d | ❌ 待测 |
| 13-8 | Gate 通过 → 自动 PR → 自动 merge 端到端验证 | P1 | 1d | 🟡 Reaction/daemon 已有基线；全链路仍待 E2E 记录 |

**验收标准**:
- 所有 12 个 LLM 节点通过 ContextAssembler 获取上下文 — **主线已满足**
- EvolutionTrigger 在每 N 次 run 后自动触发 — **🟡 策略与深度仍可增强**
- Daemon 模式下 MiniMax 实测成功记录 — **❌ 仍缺**

### Phase 14: 生产健壮性 ✅

**状态（2026-03-20）**: 全部完成。

| 编号 | 任务 | Linear | 状态 |
|------|------|--------|------|
| 14-1 | Daemon 重启恢复: 持久化进行中 issue 状态 | SON-46 | ✅ |
| 14-2 | 错误重试策略: 指数退避 + 最大重试次数 | SON-46 | ✅ |
| 14-3 | 死信队列: 多次失败的 issue 移入 dead letter | SON-46 | ✅ |
| 14-4 | Daemon Hotfix Mode: 跳过 triage + 最小 gate | SON-72 | ✅ |
| 14-5 | AI Conflict Resolution: Builder 自动解决 merge conflict | SON-68 | ✅ |

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
Phase 13 (上下文全面接入)     ← ✅ 主线已完成（2026-03-22）
    ↓
飞轮：P6 Eval / P5 Control / P4 format ← ✅ 全部基线完成（SON-190~193/202~204）
    ↓
架构债务清理                  ← ✅ 完成（PR #116，SON-206）
    ↓
Phase 14 (生产健壮性)         ← ✅ 完成（SON-44/46/68/72 Done）
    ↓
Phase 15 (Contract 自动化)    ← 待做
    ↓
Phase 16 (产品化)             ← 待做
```

**Phase 13~14 + 飞轮基线 + 架构债务均已完成**。当前阶段进入 **Phase 15 Contract 自动化** 和 **Phase 16 产品化**。外部用户端到端验证仍是关键缺口——见 **[方向性文档 §6.4](../architecture/2026-03-19-directional-review.zh.md)**。

---

## 六、与设计文档的对照检查

| 设计文档 | 当前实现状态 | 未覆盖项 |
|----------|------------|---------|
| orchestration-brain-design.md | 三流程骨架 ✅, 6 Evolver ✅, 升降级 ✅ | Memory→Evolution 数据管道的深度连接 |
| context-contract-design.md | Phase 0-3 基础设施 ✅ | ContextAssembler 全面接入 (Phase 13) |
| evolution-trigger-architecture.md | Config-driven trigger ✅ | ✅ LifecycleEvolver protocol + 跨平台文件锁 |
| spec-contract-integration.md | 手动 contract ✅ (T3.3 实验) | 自动生成 (Phase 15) |
| skill-driven-vs-spec-driven.md | 混合取舍已确认 ✅ | Skill 化的深入 (长期) |
| sdd-landscape-and-positioning.md | 行业定位确认 ✅ | — |

---

## 七、总结

spec-orch 已经完成了从"原型"到"功能完备的编排系统"的跨越。12 个 Phase/Epic
全部完成，覆盖了核心管线、可插拔适配器、自进化体系、上下文治理等关键能力。

**2026-03-22**：**Phase 13 主线（ContextAssembler 全节点 + 统一 artifact 消费路径）已落地**，不再处于「全面接入待做」。

**2026-03-20 架构债务清理**（PR #116，SON-206）：
- 原子文件写入（`atomic_write_json/text`，跨平台文件锁）
- LifecycleEvolver 4 阶段协议对齐（6 个 Evolver + 多态分发）
- RunController 拆分（RunEventLogger + RunReportWriter）
- `services/` 子包化（evolution/ builders/ context/）
- CLI 模块化（`cli/` 10 个子模块替代 4092 行单文件）
- LLM JSON 输出 schema 验证 + fallback
- 删除废弃 `pi_codex` adapter
- Evolution counter 进程锁 + PlanStrategyEvolver propose 修复

Linear 中 170 个 issue Done / 16 个 Canceled，无 open issue。1176+ 测试通过。

当前阶段更接近 **「方向性飞轮中 P5/P6/P4 与外部验证、进化深度」** — 以 [方向性文档 §6](../architecture/2026-03-19-directional-review.zh.md) 为准。
