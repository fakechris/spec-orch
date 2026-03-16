# PRD: Muscle Evolvers — 意图/流程/门控进化 + Memory 数据管道

> **Change**: 03-muscle-evolvers  
> **Linear Issues**: SON-111, SON-112, SON-113, SON-114  
> **依赖**: 01-scaffold-flow-engine（升降级事件）  
> **状态**: 草稿

## Background

Self-Evolution 已实现 4 个进化器：PromptEvolver、PlanStrategyEvolver、HarnessSynthesizer、PolicyDistiller，均依赖 EvidenceAnalyzer 从 `.spec_orch_runs` 读取历史证据。Change 01 引入 FlowEngine 后，系统开始产出**升降级事件**；Conductor 的 Intent 分类与 Gate 判定也产生可学习信号。当前这些信号分散在 EventBus、Memory 中，未被进化器消费。

编排大脑设计确立「骨架确定性 + 肌肉智能化」：骨架层（FlowEngine）已就绪，肌肉层需 3 个新进化器 + 一条从 Memory 到进化器的数据管道，形成闭环学习。

## Problem

1. **Intent 分类无反馈**：Conductor 的 classifier prompt 固定，无法从历史分类准确率、升降级结果中学习。
2. **Flow 选择阈值静态**：Intent→Flow 映射的阈值（如 confidence、改动量）手写，无法根据 promotion/demotion 事件自动调整。
3. **Gate 策略无自优化**：gate.policy.yaml 手写，Gate 的 pass/fail 与下游实际结果（merge、retro 质量）无关联，无法检测 false positive/negative。
4. **Memory 与进化器脱节**：4 层 Memory（working/episodic/semantic/procedural）已存在，但进化器仍只读 `.spec_orch_runs`，未利用 Memory 的语义化查询与事件订阅能力。

## Goal

- **IntentEvolver**：从 Episodic Memory 的 intent 日志 + 升降级事件学习，改进 Conductor classifier prompt，支持 A/B 测试与 promote。
- **FlowPolicyEvolver**：从 promotion/demotion 事件学习，调整 Intent→Flow 选择阈值（confidence、改动量等）。
- **GatePolicyEvolver**：从 Gate verdict + 下游结果学习，检测 false positive/negative，产出 gate.policy.yaml 建议。
- **Memory→Evolution 数据管道**：将 4 层 Memory 与 3 个新进化器 + 4 个既有进化器连接，定义事件类型、查询模式、存储格式。

## Non-goals

- **不替换 Conductor 核心**：IntentEvolver 仅改进 classifier prompt，不改变 Conductor 的 explore/crystallize 主流程。
- **不实现 Policy Distiller 的零 LLM 执行**：Policy Distiller 的「代码即策略」能力保持现有实现，本 change 不扩展。
- **不实现 Memory 的向量检索**：若 MemoryProvider 仅支持关键词匹配，本 change 不强制引入 embedding。
- **不自动合并 gate.policy.yaml**：GatePolicyEvolver 产出建议，人工审核后合并。

## User Scenarios

### 场景 1：Intent 分类准确率提升

系统运行 50 次后，IntentEvolver 分析 Episodic Memory 中的 intent 日志：发现「quick_fix 被误判为 feature」占 12%。LLM 生成改进版 classifier prompt，A/B 测试 10 次后 promote，新 prompt 成为默认。

### 场景 2：Flow 选择阈值自适应

多次 promotion_required 事件显示：confidence 0.6 的 quick_fix 常被选为 Standard，但实际需 Full。FlowPolicyEvolver 将 quick_fix→Standard 的 confidence 阈值从 0.6 提高到 0.75，减少误选。

### 场景 3：Gate 策略优化

Gate 多次 pass 的 issue 在 merge 后出现 regression。GatePolicyEvolver 检测到 false positive 模式，建议在 gate.policy.yaml 中增加「改动涉及 tests/ 时需额外验证」规则。

### 场景 4：进化器统一从 Memory 拉取数据

EvidenceAnalyzer 扩展为可配置数据源：除 `.spec_orch_runs` 外，可查询 Episodic Memory（intent 日志、升降级）、Semantic Memory（策略摘要）、Procedural Memory（gate 历史）。各进化器通过统一接口获取上下文。

## Success Metrics

| 指标 | 目标 | 验证方式 |
|------|------|---------|
| Intent 分类准确率 | 有 baseline 时，evolve 后误判率下降 ≥10% | 回测 Episodic Memory 中的 intent 日志 |
| Flow 误选率 | promotion_required 事件频率下降 | 对比 evolve 前后 30 天事件数 |
| Gate false positive | 可检测并产出建议 | 人工审核 GatePolicyEvolver 输出 |
| 数据管道连通 | 4 层 Memory 至少各有一个进化器消费 | 单元测试 + 集成测试 |
| 既有进化器兼容 | PromptEvolver、PlanStrategyEvolver 等行为不变 | 回归测试 |

## Risks / Open Questions

1. **Episodic Memory 容量**：intent 日志与升降级事件累积可能膨胀，需 TTL 或采样策略。
2. **LLM 调用成本**：3 个新进化器均需 LLM 生成建议，evolve 触发频率需可配置。
3. **gate.policy.yaml 冲突**：GatePolicyEvolver 建议与手写规则可能重叠，需合并策略与优先级说明。
4. **Conductor 与 RunController 时序**：Conductor 建议降级时 RunController 可能尚未启动，升降级事件需与 issue 生命周期关联。

## 与既有进化器关系

| 既有进化器 | 本 change 影响 |
|-----------|----------------|
| PromptEvolver | 无修改；IntentEvolver 借鉴其 A/B 测试模式 |
| PlanStrategyEvolver | 可选：EvidenceAnalyzer 扩展后，可消费 Semantic Memory |
| HarnessSynthesizer | 无修改 |
| PolicyDistiller | 可选：可消费 Procedural Memory 中的已蒸馏策略 |
| EvidenceAnalyzer | 扩展：支持 Memory 作为可选数据源 |

## 术语

- **EODF**：explore → freeze → plan → promote → execute → verify → gate → PR → merge → retro 的完整流程。
- **promotion_required**：Gate 发现实际改动超预期，要求升级到更严格流程（如 Standard→Full）。
- **demotion_suggested**：Conductor 或 Gate 建议可降级到更轻量流程。