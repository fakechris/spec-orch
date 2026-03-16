# 技术设计：Muscle Evolvers

> **Change**: 03-muscle-evolvers | **跨模块**：3 新服务 + Memory 集成 + EventBus 布线

## 1. 通用 Evolver 接口

既有 4 个进化器共性：`load_*()`、`evolve()`、依赖 EvidenceAnalyzer、产出存磁盘。建议新增 `EvolverProtocol`（可选）：

```python
class EvolverProtocol(Protocol):
    def load(self) -> Any: ...
    def evolve(self, planner: Any | None = None) -> Any | None: ...
```

3 个新进化器实现该协议；既有进化器可渐进适配。数据源抽象：扩展 EvidenceAnalyzer 或新增 `get_evolution_context(repo_root, memory_service, use_memory)`，聚合 .spec_orch_runs + Memory，供进化器统一使用。

## 2. 新事件类型

| action | 发布方 | payload |
|--------|--------|---------|
| intent.classified | Conductor | user_message, predicted_category, confidence, thread_id |
| flow.promotion | RunController | from_flow, to_flow, trigger, issue_id, intent_category |
| flow.demotion | RunController | 同上 |
| gate.verdict | GateService | passed, gate_input, verdict_reason, issue_id |

复用 `EventTopic.CONDUCTOR`、`EventTopic.MISSION_STATE`、`EventTopic.GATE_RESULT`，或在 payload 中通过 action 区分。MemoryService 订阅上述事件，写入 Episodic Memory，tags 含 intent-classified、flow-promotion、flow-demotion、gate-verdict。

## 3. Memory 查询模式

Episodic 写入：key 格式 `intent-{thread_id}-{ts}`、`flow-promo-{issue_id}-{ts}` 等；metadata 存完整 payload。查询示例：

```python
# IntentEvolver
MemoryQuery(layer=EPISODIC, tags=["intent-classified"], top_k=200)
# FlowPolicyEvolver
MemoryQuery(layer=EPISODIC, tags=["flow-promotion","flow-demotion"], top_k=100)
```

FileSystemMemoryProvider 需支持多 tag 查询，OR/AND 语义需明确。

## 4. 进化器解耦

依赖方向：EventBus → MemoryService → Episodic Memory；进化器仅通过 recall() 获取数据，不互相调用。CLI：`spec-orch evolve intent [--promote]`、`flow-policy [--apply]`、`gate-policy`；进化器可并行执行。

## 5. 存储格式

产出目录 `.spec_orch_evolution/`：`classifier_prompt_history.json`（与 PromptEvolver 格式类似）、`flow_policy_suggestions.json`（suggestions 列表含 intent_category、confidence_min、rationale）、`gate_policy_suggestions.yaml`（suggested_rules 片段）。不自动合并，人工审核后合并。

## 6. 模块清单

| 新增 | 职责 |
|------|------|
| intent_evolver.py | IntentEvolver |
| flow_policy_evolver.py | FlowPolicyEvolver |
| gate_policy_evolver.py | GatePolicyEvolver |
| evolver_protocol.py | EvolverProtocol（可选） |

| 修改 | 变更 |
|------|------|
| event_bus.py | 新 payload 结构 |
| memory/service.py | 订阅新事件，写入 Episodic |
| conductor/intent_classifier.py | 发布 intent.classified |
| gate_service.py | 发布 gate.verdict |
| flow_mapper | 阈值覆盖 |
| evidence_analyzer.py | 可选 Memory 数据源 |
| cli.py | evolve 子命令 |

## 7. 实现顺序建议

1. 先实现事件发布与 Memory 写入（阶段 1），确保数据管道连通。
2. 三个进化器可并行开发（阶段 2），互不依赖。
3. EvidenceAnalyzer 扩展与 flow_mapper 集成（阶段 3）可最后完成。
4. Conductor 加载 IntentEvolver prompt 可作为后续迭代，本 change 可仅产出 history 供人工复制。

## 8. 测试策略

- 单元测试：各进化器在无 Memory 数据时返回空/None，不抛错。
- 集成测试：mock EventBus 发布事件 → Memory 写入 → 进化器 recall → evolve 产出非空。
- 回归测试：既有 PromptEvolver、PlanStrategyEvolver 的 CLI 与行为不变。
- 性能：evolve 为离线操作，不阻塞主流程；可配置为 cron 或手动触发。