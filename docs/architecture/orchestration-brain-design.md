# 编排大脑设计：骨架确定性 + 肌肉智能化

> 日期: 2026-03-14
> 状态: 设计哲学确认，待实施
> Linear Epic: SON-100 (混合架构: Talk Freely, Execute Strictly)
> 前置文档:
> - [SDD 行业全景](sdd-landscape-and-positioning.md)
> - [Skill-Driven vs Spec-Driven](skill-driven-vs-spec-driven.md)
> - [Change Management Policy](change-management-policy.md)

## 一、核心问题

spec-orch 的"大脑"到底应该是写死的确定性逻辑，还是一个能动态协调的
超级智能体？

**答案：两层分离。**

- **骨架层 (Scaffold)** — 确定性，代码写死。定义流程拓扑、步骤转换条件、
  回退路径。可测试、可审计、可 debug。
- **肌肉层 (Muscle)** — LLM 驱动，可进化。每个步骤内部的执行逻辑由
  prompt/skill 定义，通过 evidence 反馈持续改进。

这个结论来自对学术研究的综合分析：SEW、MetaAgent、Live-SWE-agent、
VIGIL 四个系统的共同设计模式都是——骨架确定性，节点智能化，进化发生在
节点级别而非骨架级别。

## 二、流程设计

### 2.1 三种流程足矣

保持 [change-management-policy.md](change-management-policy.md) 已定义的三种：

| 流程 | 适用场景 | 核心步骤 |
|------|---------|---------|
| **Full** | 新功能、架构变更 | 需求→spec→plan→promote→execute→gate→retro |
| **Standard** | Bug 修复、小改进 | issue→implement→verify→gate→PR |
| **Hotfix** | 生产阻断、安全问题 | issue→fix→minimal-gate→merge→post-review |

不再增加新的流程类型。灵活性不在于"更多流程"，而在于：

1. **步骤可跳过 (Step Skippability)** — 每个步骤标注可跳过条件
   （如 doc-only 变更跳过 verify 中的 test 子步骤）
2. **流程升降级 (Flow Promotion/Demotion)** — 运行中可升级或降级，
   由 Gate 的后验检查触发

### 2.2 流程升降级机制

```
Full ──┐
       │ demotion: Gate 发现改动量小于预期
       ▼
Standard ──┐
           │ demotion: Gate 发现无代码变更 (doc-only)
           ▼
        Hotfix
           │
           │ promotion: Gate 发现改动量超预期 / 涉及架构变更
           ▼
        Standard / Full
```

升降级规则：

- **降级**由 Conductor (Intent) 前置判断建议，Gate 后验确认
- **升级**由 Gate 强制触发——如果"声称只改文档"但实际改了代码，
  Gate 拒绝当前流程并要求升级到 Standard
- 升降级事件记录到 Episodic Memory，供 FlowPolicyEvolver 学习

### 2.3 流程选择：Intent → Flow Mapping

Conductor 的 Intent 分类直接映射到流程选择：

| IntentCategory | 默认流程 | 可降级? | 可升级? |
|----------------|---------|---------|---------|
| Feature | Full | 是 (如果范围小) | - |
| Bug | Standard | 是 (如果紧急) | 是 (如果涉及架构) |
| Quick_Fix | Standard | 是 (到 Hotfix) | 是 (如果范围超预期) |
| Exploration | 不进入流程 | - | 是 (Crystallize 后) |
| Question | 不进入流程 | - | - |
| Drift | 创建新 Issue | - | - |

### 2.4 非线性处理

**分裂 (Fork)**：对话中识别到新意图时，不中断当前流程，而是：
1. Conductor 检测到 Drift 或新的 Actionable Intent
2. 自动创建新 Linear Issue（记录来源 thread 和原始 intent）
3. 当前流程继续执行
4. 新 Issue 进入独立的流程选择

**回退 (Backtrack)**：Gate 发现问题时：
1. Gate 判定 fail + 原因分类（recoverable / needs_redesign / promotion_required）
2. `recoverable` → 回到 Execute 阶段重试
3. `needs_redesign` → 回到 Spec/Plan 阶段
4. `promotion_required` → 流程升级，从新流程的起点开始

## 三、进化体系

### 3.1 核心原则：进化肌肉，不进化骨架

骨架（3 种流程的有向图、步骤转换条件）是固定的，不参与进化。
进化发生在肌肉层——每个节点内部的判断逻辑。

### 3.2 进化对象矩阵

| 进化对象 | 数据来源 | 进化机制 | 状态 |
|----------|---------|---------|------|
| Builder Prompt | 历史 run 成功率 | A/B 测试 + 自动晋升 | **已有** (PromptEvolver) |
| Plan Strategy | 历史 plan 拆分效果 | Scoper hints 注入 | **已有** (PlanStrategyEvolver) |
| Compliance Rules | 历史失败模式 | LLM 合成 + 回测验证 | **已有** (HarnessSynthesizer) |
| Routine Tasks | 重复任务模式 | 蒸馏为 Python 脚本 | **已有** (PolicyDistiller) |
| **Intent Classifier** | intent 分类 vs 实际流程 | 准确率统计 + prompt 调优 | **待建** |
| **Flow Selection** | 流程选择 vs Gate 后验 | 升降级统计 → 阈值调整 | **待建** |
| **Gate Policy** | Gate 判定 vs 实际结果 | 统计分析 + 阈值调整 | **待建** |

### 3.3 进化数据流

```
执行 ──→ Evidence (Episodic Memory)
              │
              ├──→ PromptEvolver        (builder prompt 成功率)
              ├──→ PlanStrategyEvolver   (plan 拆分效果)
              ├──→ HarnessSynthesizer    (失败模式 → 合规规则)
              ├──→ PolicyDistiller       (重复任务 → 代码)
              ├──→ IntentEvolver (新)    (intent 分类准确率)
              ├──→ FlowPolicyEvolver (新)(升降级事件 → 阈值)
              └──→ GatePolicyEvolver (新)(Gate 判定 vs 后果)
                       │
                       ▼
              改进后的 artifacts ──→ 下一次执行
```

### 3.4 Memory 与进化的连接

| Memory 层 | 存储内容 | 驱动哪些进化器 |
|-----------|---------|--------------|
| Working | 当前对话上下文 | Conductor intent 分类 |
| Episodic | 每次 run 的记录 | PromptEvolver, PlanStrategyEvolver, IntentEvolver |
| Semantic | 抽象知识（模式、规律） | Gate Policy, Compliance Rules |
| Procedural | "怎么做"的知识 | PolicyDistiller (蒸馏为代码) |

新增的数据流需要建设：
- **Intent 判定日志** → Episodic → IntentEvolver
- **Flow 升降级事件** → Episodic → FlowPolicyEvolver
- **Gate 后验结果**（Gate 说 pass 但后来发现有问题）→ Semantic → GatePolicyEvolver

## 四、学术支撑

| 论文/系统 | 核心启示 | 对 spec-orch 的影响 |
|----------|---------|-------------------|
| **SEW** (arXiv 2505.18646) | 自动进化 agent 拓扑和 prompt | 进化肌肉层 prompt，不进化骨架拓扑 |
| **MetaAgent** (arXiv 2508.00271) | 从最小工作流开始，learning-by-doing | 新能力应从 evidence 中涌现，不靠预设 |
| **Live-SWE-agent** (arXiv 2511.13646) | 运行时自主扩展能力，SWE-bench 77.4% | Conductor 可运行时发现新 intent 类别 |
| **VIGIL** (arXiv 2512.07094) | 行为日志→诊断→自动修复 prompt | Intent 错分→日志记录→自动调优 classifier |
| **Anthropic Patterns** | 5 种 workflow pattern + "简单优先" | 骨架用 routing + orchestrator-workers |
| **OpenAI Handoffs** | Triage agent → specialist handoff | Conductor = triage，流程阶段 = specialists |

## 五、设计原则总结

1. **骨架确定性，肌肉智能化** — 流程图写死（3 种），每个节点内部 LLM 执行
2. **三种流程足矣** — Full / Standard / Hotfix，灵活性靠 step skippability
   和 flow promotion/demotion
3. **Gate 是终极仲裁** — 不管 Intent 怎么判，Gate 的后验检查说了算
4. **进化肌肉，不进化骨架** — PromptEvolver, IntentEvolver, FlowPolicyEvolver
   都是肌肉层
5. **Evidence 驱动一切** — 每个进化决策都有数据支撑，不靠猜测
6. **分裂可以，但要有审计** — Fork 出新 issue 必须记录来源 thread 和原始 intent
7. **不做超级大脑** — Conductor 是 triage agent 不是全知全能的超级智能体；
   它只做分类和路由，不做执行决策
