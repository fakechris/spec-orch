# 变更提案：Muscle Evolvers

> **Change**: 03-muscle-evolvers  
> **Linear Issues**: SON-111, SON-112, SON-113, SON-114  
> **依赖**: 01-scaffold-flow-engine

## Why

1. **进化闭环不完整**：4 个既有进化器（PromptEvolver、PlanStrategyEvolver、HarnessSynthesizer、PolicyDistiller）仅消费 `.spec_orch_runs` 证据，Conductor 的 Intent 分类、Flow 选择、Gate 判定产生的信号未被利用。
2. **Change 01 产出未消费**：scaffold-flow-engine 引入 promotion/demotion 事件并写入 Episodic Memory，但无进化器读取这些事件。
3. **编排大脑肌肉层缺失**：骨架层（FlowEngine）已就绪，肌肉层需 3 个新进化器 + Memory 数据管道，使 Intent→Flow→Gate 全链路可学习。
4. **Memory 与进化器脱节**：MemoryService 有 store/recall/subscribe_to_event_bus，4 层 Memory 已定义，但进化器仍只读文件系统。

## What Changes

### 新增能力

- **IntentEvolver**：从 Episodic Memory 的 intent 日志 + 升降级事件学习，改进 Conductor classifier prompt；支持 load_history、record_run、evolve、ab_test、promote_winner，与 PromptEvolver 模式一致。
- **FlowPolicyEvolver**：从 promotion/demotion 事件学习，调整 flow_mapping.yaml 中的阈值（confidence、改动量等）；产出 flow_policy_suggestions.json。
- **GatePolicyEvolver**：从 Gate verdict + 下游结果（merge、retro）学习，检测 false positive/negative；产出 gate.policy.yaml 建议片段，供人工审核合并。
- **Memory→Evolution 数据管道**：定义 4 层 Memory 与各进化器的数据流；新增 EventTopic 子类型（intent.classified、flow.promotion、flow.demotion、gate.verdict）；EvidenceAnalyzer 扩展为可配置数据源（Memory + 文件系统）。

### 修改现有模块

- **event_bus.py**：扩展 EventTopic 或 payload 结构，支持 intent.classified、flow.promotion、flow.demotion、gate.verdict 等事件。
- **memory/service.py**：MemoryService 订阅新事件类型，将 intent 分类、升降级、Gate 结果写入对应 Memory 层。
- **conductor/intent_classifier.py**：分类后发布 intent.classified 事件；可选：支持从 IntentEvolver 加载 prompt 变体。
- **flow_mapper**（Change 01 引入）：支持从 FlowPolicyEvolver 加载阈值覆盖。
- **gate_service.py**：evaluate 后发布 gate.verdict 事件，payload 含 verdict、gate_input、downstream_issue_id。
- **evidence_analyzer.py**：扩展为可选 Memory 数据源，支持 MemoryQuery 参数；保持向后兼容。

### 新增模块

- **intent_evolver.py**：IntentEvolver 服务，逻辑与 PromptEvolver 类似，数据源改为 Episodic Memory。
- **flow_policy_evolver.py**：FlowPolicyEvolver 服务。
- **gate_policy_evolver.py**：GatePolicyEvolver 服务。
- **evolver_protocol.py**（可选）：提取 Evolver 通用接口，供 7 个进化器统一实现。

## What Is Explicitly Out of Scope

- Episodic Memory 的向量检索或 embedding：若当前 provider 不支持，不引入新依赖。
- 自动合并 gate.policy.yaml：GatePolicyEvolver 产出建议，人工审核后合并。
- 跨 Issue 依赖编排（Change 04）。
- Conductor Fork 逻辑（Change 02）：本 change 仅消费 Intent 分类结果，不修改 fork 触发条件。
- Policy Distiller 的零 LLM 执行扩展：保持现有能力。

## Impacted Areas

| 模块 | 影响类型 | 说明 |
|------|---------|------|
| `services/intent_evolver.py` | 新增 | IntentEvolver |
| `services/flow_policy_evolver.py` | 新增 | FlowPolicyEvolver |
| `services/gate_policy_evolver.py` | 新增 | GatePolicyEvolver |
| `services/evolver_protocol.py` | 新增（可选） | 通用 Evolver 接口 |
| `services/event_bus.py` | 扩展 | 新事件类型 |
| `services/memory/service.py` | 扩展 | 订阅新事件，写入 Memory |
| `services/conductor/intent_classifier.py` | 扩展 | 发布 intent.classified，可选加载 evolver prompt |
| `services/evidence_analyzer.py` | 扩展 | Memory 数据源 |
| `flow_mapper` | 扩展 | 阈值覆盖 |
| `services/gate_service.py` | 扩展 | 发布 gate.verdict |
| CLI | 新增 | `spec-orch evolve intent`、`flow-policy`、`gate-policy` |

## Migration Path

1. **渐进启用**：新事件发布与 Memory 写入先上线，进化器可后续分批接入。
2. **默认关闭**：IntentEvolver 的 prompt 变体加载可配置，默认仍用现有 classifier prompt。
3. **向后兼容**：无 Memory 数据时，各进化器优雅降级，返回空建议，不抛错。
4. **人工审核**：FlowPolicyEvolver、GatePolicyEvolver 产出均需人工审核后合并，不自动覆盖配置。

## 与 Change 01/02 衔接

- Change 01 的 FlowTransitionEvent、GateVerdict 扩展为本 change 的事件 payload 提供数据模型。
- Change 02 的 conductor.fork 事件与 intent 分类独立；IntentEvolver 仅消费分类结果，不修改 fork 逻辑。

## 配置项（可选）

- `SPEC_ORCH_EVOLVE_INTENT_ENABLED`：是否启用 IntentEvolver prompt 加载，默认 false。
- `SPEC_ORCH_EVOLVE_MIN_RUNS`：触发 evolve 的最小运行次数，默认 20。
- `SPEC_ORCH_EVOLUTION_DIR`：进化器产出目录，默认 `.spec_orch_evolution`。