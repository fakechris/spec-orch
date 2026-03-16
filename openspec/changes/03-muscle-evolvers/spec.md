# 需求规格：Muscle Evolvers

> **Change**: 03-muscle-evolvers | **依赖**: 01-scaffold-flow-engine

## 1. IntentEvolver

### 1.1 数据源

| 需求 | 描述 |
|------|------|
| **R1.1** Episodic Memory intent 日志 | `MemoryService.recall()` 查询 `MemoryLayer.EPISODIC`，tags 含 `intent-classified`；每条记录含：user_message、predicted_category、confidence、timestamp。 |
| **R1.2** 升降级事件 | 查询 tags 含 `flow-promotion` 或 `flow-demotion`；与 intent 日志通过 issue_id/thread_id 关联，用于判断「该 intent 对应的 flow 选择是否合理」。 |

### 1.2 机制

| 需求 | 描述 |
|------|------|
| **R1.3** 准确率统计 | 从 intent 日志 + 升降级事件计算：误判率（按 category）、promotion_required 与 intent 的关联、demotion_suggested 与 intent 的关联。 |
| **R1.4** 模式检测 | 识别高频误判模式（如「quick_fix 被误判为 feature」），作为 LLM 改进 prompt 的输入。 |
| **R1.5** Prompt 改进 | LLM 生成改进版 classifier prompt，保持与现有 prompt 结构兼容；输出格式与 PromptEvolver 的 variant 类似。 |
| **R1.6** A/B 测试 | 新 prompt 作为 candidate，与当前 active 并行运行 N 次（可配置），比较准确率。 |
| **R1.7** Promote 获胜者 | 当 candidate 胜出且置信度足够时，promote 为 active，写入 classifier_prompt_history.json。 |

### 1.3 输出

| 需求 | 描述 |
|------|------|
| **R1.8** 历史文件 | `classifier_prompt_history.json`：variant_id、prompt_text、rationale、total_runs、successful_runs、is_active、is_candidate。 |
| **R1.9** CLI | `spec-orch evolve intent`：触发 load_history、evolve、可选 ab_test；`--promote` 显式 promote 当前 candidate。 |

### 1.4 错误处理

| 需求 | 描述 |
|------|------|
| **R1.10** Memory 无数据 | 若 Episodic Memory 无 intent 日志，evolve 返回空，记录 info 日志，不抛错。 |
| **R1.11** LLM 失败 | 捕获异常，记录日志，返回 None；不修改现有 prompt。 |

---

## 2. FlowPolicyEvolver

### 2.1 数据源

| 需求 | 描述 |
|------|------|
| **R2.1** 升降级事件 | 查询 `MemoryLayer.EPISODIC`，tags 含 `flow-promotion`、`flow-demotion`；payload 含 from_flow、to_flow、trigger、issue_id、intent_category、confidence。 |
| **R2.2** 既有 flow_mapping | 读取 flow_mapping.yaml（Change 01 引入），获取当前 Intent→Flow 映射与阈值。 |

### 2.2 阈值调整机制

| 需求 | 描述 |
|------|------|
| **R2.3** 模式分析 | 统计 promotion_required 与 demotion_suggested 的分布：按 intent_category、confidence 区间、改动量。 |
| **R2.4** 阈值建议 | LLM 或规则引擎产出：建议提高/降低某 (intent, flow) 的 confidence 阈值；或新增改动量阈值。 |
| **R2.5** 输出格式 | `flow_policy_suggestions.json`：suggestions 列表，每项含 intent_category、flow_type、confidence_min、change_threshold、rationale。 |

### 2.3 输出

| 需求 | 描述 |
|------|------|
| **R2.6** 建议文件 | 不直接修改 flow_mapping.yaml；产出建议文件供人工审核或 `--apply` 合并。 |
| **R2.7** CLI | `spec-orch evolve flow-policy`：触发 load、evolve、输出建议。 |

### 2.4 错误处理

| 需求 | 描述 |
|------|------|
| **R2.8** 无升降级事件 | 若 Episodic Memory 无相关事件，返回空建议列表，记录 info 日志。 |
| **R2.9** flow_mapping 缺失 | 若 flow_mapping.yaml 不存在，使用默认映射，记录 warning。 |

---

## 3. GatePolicyEvolver

### 3.1 数据源

| 需求 | 描述 |
|------|------|
| **R3.1** Gate verdict | 查询 `MemoryLayer.EPISODIC`，tags 含 `gate-verdict`；payload 含 passed、gate_input、verdict_reason、issue_id。 |
| **R3.2** 下游结果 | 从 Episodic Memory 或 `.spec_orch_runs` 获取：merge 后是否有 regression、retro 质量、用户反馈。 |
| **R3.3** 既有 gate.policy.yaml | 读取当前 gate 策略，作为 baseline。 |

### 3.2 False Positive / Negative 检测

| 需求 | 描述 |
|------|------|
| **R3.4** False positive | Gate pass 但下游出现 regression 或负面反馈；记录 pattern（如涉及目录、改动量、验证类型）。 |
| **R3.5** False negative | Gate fail 但人工 override 后 merge 成功且无问题；记录 pattern。 |
| **R3.6** 建议生成 | LLM 分析 failure 模式，产出 gate.policy.yaml 兼容的规则片段（如新增 rule、调整 severity、新增 profile 条件）。 |

### 3.3 输出

| 需求 | 描述 |
|------|------|
| **R3.7** 建议文件 | `gate_policy_suggestions.yaml`：YAML 片段，含 suggested_rules、rationale、source_issues；不自动合并。 |
| **R3.8** CLI | `spec-orch evolve gate-policy`：触发 load、evolve、输出建议。 |

### 3.4 错误处理

| 需求 | 描述 |
|------|------|
| **R3.9** 无 Gate 数据 | 若 Episodic Memory 无 gate-verdict，返回空建议，记录 info 日志。 |
| **R3.10** 下游结果缺失 | 若无法获取 merge/retro 数据，仅基于 Gate verdict 做有限分析，记录 warning。 |

---

## 4. Memory→Evolution 数据管道

### 4.1 Memory 层与进化器映射

| Memory 层 | 消费进化器 | 查询模式 |
|-----------|----------|----------|
| **Episodic** | IntentEvolver, FlowPolicyEvolver, GatePolicyEvolver | tags: intent-classified, flow-promotion, flow-demotion, gate-verdict |
| **Semantic** | PlanStrategyEvolver（可选） | 策略摘要、hint 历史 |
| **Procedural** | PolicyDistiller（可选） | 已蒸馏策略 |
| **Working** | 不直接消费 | 会话级临时数据 |

### 4.2 新事件类型

| 事件 | 发布方 | 写入 Memory 层 | tags |
|------|--------|---------------|------|
| intent.classified | Conductor | Episodic | intent-classified |
| flow.promotion | RunController | Episodic | flow-promotion |
| flow.demotion | RunController | Episodic | flow-demotion |
| gate.verdict | GateService | Episodic | gate-verdict |

### 4.3 查询模式

| 进化器 | MemoryQuery 示例 |
|--------|------------------|
| IntentEvolver | layer=EPISODIC, tags=[intent-classified], top_k=200 |
| FlowPolicyEvolver | layer=EPISODIC, tags=[flow-promotion, flow-demotion], top_k=100 |
| GatePolicyEvolver | layer=EPISODIC, tags=[gate-verdict], top_k=100 |
| EvidenceAnalyzer | 扩展：可选 layer=EPISODIC, tags=[issue-result] |

### 4.4 兼容性

| 需求 | 描述 |
|------|------|
| **R4.1** 既有进化器 | PromptEvolver、PlanStrategyEvolver、HarnessSynthesizer、PolicyDistiller 保持现有行为；EvidenceAnalyzer 扩展为可选 Memory 源，默认仍读 `.spec_orch_runs`。 |
| **R4.2** 解耦 | 各进化器通过 MemoryService.recall() 与 EventBus 订阅获取数据，不直接依赖其他进化器；进化器间无调用链。 |
| **R4.3** 存储格式 | 进化器产出（history、suggestions）仍存于 repo 根或 `.spec_orch_evolution/`，不写入 Memory 层。 |

---

## 5. 场景验收

- **场景 A（Intent）**：运行 50 次后，`spec-orch evolve intent` 产出新 prompt variant，A/B 测试 10 次后 promote，Conductor 使用新 prompt。
- **场景 B（Flow）**：多次 promotion_required 后，`spec-orch evolve flow-policy` 产出建议，人工审核后合并到 flow_mapping.yaml。
- **场景 C（Gate）**：Gate pass 后 merge 出现 regression，`spec-orch evolve gate-policy` 产出建议规则。
- **场景 D（管道）**：Conductor 分类后发布 intent.classified，MemoryService 写入 Episodic；IntentEvolver 通过 recall 获取日志。