# Proposal: scaffold-flow-engine

> **Change**: 01-scaffold-flow-engine  
> **Linear Issues**: SON-107, SON-108, SON-109

## Why

1. **策略与实现脱节**：change-management-policy 定义了 Full / Standard / Hotfix 三种层级，但 RunController 未区分，所有变更走同一隐式流程。
2. **无法响应后验信息**：Gate 在 verify 后能发现「实际改动与声称不符」，但无法触发流程升级或降级。
3. **编排大脑设计要求**：orchestration-brain-design 明确要求骨架层确定性、步骤可跳过、流程可升降级，当前实现不满足。
4. **进化数据缺失**：升降级事件需记录到 Episodic Memory，供 FlowPolicyEvolver 学习，但当前无此类事件模型。

## What Changes

### 新增能力

- **FlowType 枚举**：Full / Standard / Hotfix，与 change-management-policy 一一对应。
- **FlowGraph 定义**：每种 FlowType 对应一个 DAG，包含步骤序列、转换条件、可跳过条件、回退路径。
- **FlowEngine 模块**：根据 FlowType 返回当前步骤、下一可达步骤、回退目标；不包含业务逻辑，纯拓扑查询。
- **Intent → Flow 映射**：可配置规则（YAML），将 Conductor 的 IntentCategory 映射到 FlowType，支持默认与覆盖。
- **Gate 升降级信号**：GateVerdict 扩展，支持 `promotion_required`、`demotion_suggested` 等；GateService 在 evaluate 时产出这些信号。
- **RunController 集成**：run 前根据 issue 元数据或 Conductor 建议选择 FlowType；执行中根据 Gate 信号决定是否升降级、回退。
- **升降级事件模型**：`FlowTransitionEvent` 数据类，记录 from_flow、to_flow、trigger、timestamp，供 Episodic Memory 写入。

### 修改现有模块

- **domain/models.py**：新增 FlowType、FlowStep、FlowGraph、FlowTransition、FlowTransitionEvent；GateVerdict 增加可选字段。
- **gate_service.py**：evaluate 时根据 GateInput 计算 promotion/demotion 信号，写入 GateVerdict。
- **run_controller.py**：引入 FlowEngine，按 FlowGraph 驱动步骤推进；处理 Gate 返回的升降级信号。
- **conductor/types.py**：无修改；Conductor 通过新模块 `flow_mapper` 查询 Intent→Flow，不直接依赖 types。

### 新增模块

- **flow_engine/**：FlowGraph 定义、FlowEngine 类、step 查询与转换逻辑。
- **flow_mapper**：加载 Intent→Flow 配置，提供 `resolve_flow_type(intent, issue_metadata) -> FlowType`。

## What Is Explicitly Out of Scope

- Episodic Memory 的持久化实现（仅定义事件模型与写入接口）。
- Conductor Fork（SON-110）：本 change 不实现对话中分裂出新 issue 的逻辑。
- Muscle Evolvers（IntentEvolver、FlowPolicyEvolver、GatePolicyEvolver）：本 change 仅提供数据产出，进化逻辑由后续 change 实现。
- Hotfix 的 Daemon 自动拉取与优先调度：流程定义完成即可，调度策略不在此 scope。
- 完全动态的工作流引擎：不支持用户自定义新流程类型。

## Impacted Areas

| 模块 | 影响类型 | 说明 |
|------|---------|------|
| `domain/models.py` | 新增类型 | FlowType, FlowStep, FlowGraph, FlowTransition, FlowTransitionEvent；GateVerdict 扩展 |
| `services/gate_service.py` | 行为扩展 | 产出 promotion/demotion 信号 |
| `services/run_controller.py` | 行为重构 | 按 FlowGraph 驱动，处理升降级 |
| `services/conductor/` | 集成 | 通过 flow_mapper 解析 Intent→Flow，不修改 Conductor 核心 |
| 新增 `flow_engine/` | 新模块 | FlowGraph 定义、FlowEngine |
| 新增 `flow_mapper` | 新模块 | Intent→Flow 配置加载与解析 |
| 配置 | 新增 | `flow_mapping.yaml` 或等价配置 |

## Migration Path

1. **默认行为保持不变**：未指定 flow 且无 Intent 时，默认使用 Standard 流程（与当前 RunController 行为最接近）。
2. **渐进启用**：通过 feature flag 或配置开关控制是否启用 FlowEngine；关闭时 RunController 保持现有逻辑。
3. **向后兼容**：现有 CLI、Daemon 调用方式不变；新增可选参数 `--flow` 用于显式指定。

## 与编排大脑设计的对应关系

- **骨架确定性**：FlowGraph 预定义，不参与进化。
- **步骤可跳过**：FlowStep.skippable_if 支持 doc_only 等条件。
- **流程升降级**：Gate 后验触发 promotion，Conductor 建议 + Gate 确认触发 demotion。
- **进化数据**：FlowTransitionEvent 写入 Episodic Memory，供 FlowPolicyEvolver 使用。

## 验收要点

- 三种 FlowType 均有完整 FlowGraph，与 change-management-policy 一致。
- Intent→Flow 可通过 YAML 配置，Linear 标签可覆盖。
- Gate 能产出 promotion/demotion/backtrack 信号，RunController 能正确响应。
- 默认 flow=Standard 时，行为与当前 RunController 等价。
