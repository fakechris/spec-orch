# 任务清单：Muscle Evolvers

> **Change**: 03-muscle-evolvers | **Linear**: SON-111, SON-112, SON-113, SON-114

## 前置

- [ ] Change 01（scaffold-flow-engine）已合并或可并行开发，promotion/demotion 事件模型可用。
- [ ] MemoryService、EventBus、MemoryLayer 已就绪。

## 阶段 1：事件与 Memory 管道（SON-114 部分）

**可并行**：1.1 与 1.2 可并行。

### 1.1 事件定义与发布

- [ ] 扩展 EventBus：定义 intent.classified、flow.promotion、flow.demotion、gate.verdict 的 payload 结构（或复用现有 topic + action）。
- [ ] Conductor intent_classifier：分类完成后发布 intent.classified 事件。
- [ ] RunController：升降级时发布 flow.promotion / flow.demotion（若 Change 01 未实现，本 change 补充）。
- [ ] GateService：evaluate 后发布 gate.verdict 事件。

### 1.2 Memory 写入

- [ ] MemoryService.subscribe_to_event_bus：订阅上述事件。
- [ ] 实现 _on_intent_classified、_on_flow_transition、_on_gate_verdict，写入 Episodic Memory，tags 正确。
- [ ] 单元测试：发布事件后 Memory 中可 recall 到对应条目。

### 1.3 查询能力

- [ ] FileSystemMemoryProvider（或 MemoryQuery）：支持按 tags 过滤，多 tag 语义明确（OR/AND）。
- [ ] 单元测试：IntentEvolver、FlowPolicyEvolver、GatePolicyEvolver 的 MemoryQuery 可正确召回数据。

---

## 阶段 2：三个进化器实现

**可并行**：2.1、2.2、2.3 可并行（互不依赖）。

### 2.1 IntentEvolver（SON-111）

- [ ] 新建 `intent_evolver.py`，实现 IntentEvolver 类。
- [ ] load_history：从 .spec_orch_evolution/classifier_prompt_history.json 加载。
- [ ] 从 Episodic Memory recall intent-classified + flow-promotion/demotion，计算准确率与误判模式。
- [ ] evolve：LLM 生成改进版 classifier prompt。
- [ ] ab_test、promote_winner：与 PromptEvolver 模式一致。
- [ ] CLI：`spec-orch evolve intent [--promote]`。
- [ ] 单元测试：无 Memory 数据时返回空；有数据时产出合理 variant。

### 2.2 FlowPolicyEvolver（SON-112）

- [ ] 新建 `flow_policy_evolver.py`，实现 FlowPolicyEvolver 类。
- [ ] 从 Episodic Memory recall flow-promotion、flow-demotion。
- [ ] 读取 flow_mapping.yaml，分析阈值与事件的关联。
- [ ] evolve：产出 flow_policy_suggestions.json。
- [ ] CLI：`spec-orch evolve flow-policy [--apply]`。
- [ ] 单元测试：无事件时返回空建议；有事件时产出合理建议。

### 2.3 GatePolicyEvolver（SON-113）

- [ ] 新建 `gate_policy_evolver.py`，实现 GatePolicyEvolver 类。
- [ ] 从 Episodic Memory recall gate-verdict。
- [ ] 从 .spec_orch_runs 或 Memory 获取下游结果（merge、retro）。
- [ ] 实现 false positive/negative 检测逻辑。
- [ ] evolve：LLM 产出 gate_policy_suggestions.yaml。
- [ ] CLI：`spec-orch evolve gate-policy`。
- [ ] 单元测试：无数据时返回空；有 false positive 模式时产出建议。

---

## 阶段 3：集成与兼容

**依赖阶段 1、2**。

### 3.1 EvidenceAnalyzer 扩展（可选）

- [ ] EvidenceAnalyzer 增加可选 Memory 数据源参数。
- [ ] 保持默认行为不变，既有进化器无感知。
- [ ] 单元测试：启用 Memory 时，analyze() 结果包含 Episodic 数据。

### 3.2 flow_mapper 阈值覆盖

- [ ] flow_mapper 支持从 flow_policy_suggestions.json 或已合并配置读取阈值覆盖。
- [ ] 当 FlowPolicyEvolver 产出且用户 --apply 时，更新 flow_mapping.yaml。

### 3.3 Conductor 集成 IntentEvolver

- [ ] intent_classifier 支持从 IntentEvolver 加载 active prompt 变体（可选，可后续迭代）。
- [ ] 若本 change 不实现，至少保证 IntentEvolver 产出的 history 可被人工复制到 classifier prompt 配置。

### 3.4 Evolver 协议（可选）

- [ ] 新建 evolver_protocol.py，定义 EvolverProtocol。
- [ ] 3 个新进化器实现该协议。
- [ ] 既有进化器可渐进适配，不强制。

---

## 阶段 4：测试与文档

- [ ] 集成测试：完整流程——Conductor 分类 → 发布事件 → Memory 写入 → IntentEvolver recall → evolve。
- [ ] 集成测试：RunController 升降级 → Memory 写入 → FlowPolicyEvolver recall → evolve。
- [ ] 集成测试：Gate evaluate → 发布事件 → Memory 写入 → GatePolicyEvolver recall → evolve。
- [ ] 回归测试：既有 PromptEvolver、PlanStrategyEvolver 等行为不变。
- [ ] 更新 openspec README 或 changelog，标注 03-muscle-evolvers 完成项。

---

## 验收

- [ ] 满足 spec.md 中 R1–R4 全部需求。
- [ ] 四个用户场景（Intent、Flow、Gate、管道）至少三个可手动验证。
- [ ] 无新增 linter 错误，现有测试通过。