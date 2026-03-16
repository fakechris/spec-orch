# Design: 骨架流程引擎

> **Change**: 01-scaffold-flow-engine  
> **类型**: 跨模块技术设计

---

## 1. 新增类型定义

**FlowType**（`domain/models.py`）：`Full` / `Standard` / `Hotfix` 枚举。

**FlowStep**：`id`, `flow_type`, `skippable_if: list[str]`, `run_state: RunState | None`。

**FlowGraph**：`flow_type`, `steps`, `transitions: dict[str, list[str]]`, `backtrack: dict[str, dict[str, str]]`（reason → target_step_id）。

**FlowTransitionEvent**：`from_flow`, `to_flow`, `trigger`, `timestamp`, `issue_id`, `run_id`。

**GateVerdict 扩展**：`promotion_required`, `promotion_target`, `demotion_suggested`, `demotion_target`, `backtrack_reason`。

**GateInput 扩展**：`claimed_flow`, `demotion_proposed_by_conductor`, `diff_stats`。

---

## 2. 模块布局

| 内容 | 位置 |
|------|------|
| FlowType, FlowStep, FlowGraph, FlowTransitionEvent | `domain/models.py` |
| FlowGraph 预定义实例 | `flow_engine/graphs.py` |
| FlowEngine（get_graph, get_next_steps, get_backtrack_target） | `flow_engine/engine.py` |
| FlowMapper（resolve_flow_type） | `flow_engine/mapper.py` |
| Intent→Flow 规则 | `flow_mapping.yaml` |

新建 `spec_orch/flow_engine/` 包。`domain/models.py` 仅放数据模型。

---

## 3. RunController 改造

- `run_issue(issue_id, flow_type=None)`：`flow = flow_type or _resolve_flow(issue)`，`_resolve_flow` 调用 FlowMapper（输入 issue.run_class、标签、Conductor 建议）。
- 维护 `current_step`、`current_flow`；每步后根据 GateVerdict 决定前进、回退、升降级。
- 升降级时：`current_flow = verdict.promotion_target`，`current_step = 新图.steps[0]`。
- FlowStep 与 RunState 映射表在 FlowGraph 定义时写死，用于兼容 GateInput、report。

---

## 4. GateService 改造

- **promotion_required**：`claimed_flow` 为 Standard/Hotfix 但 `within_boundaries=False` 或 verification 涉及代码 → True。
- **demotion_suggested**：`demotion_proposed_by_conductor` 且 `diff_stats` 在阈值内 → True。
- **backtrack_reason**：`mergeable=False` 时，根据 `failed_conditions` 推断 `recoverable` / `needs_redesign` / `promotion_required`。

---

## 5. Conductor 与 Flow 映射

Conductor 不直接依赖 FlowEngine。用户 approve 时，调用方从 `proposal.intent_category` 调用 `FlowMapper.resolve_flow_type()`，结果写入 issue 或传给 RunController。建议降级可放在 `ConductorState` 或 issue 扩展字段。

---

## 6. 升降级事件与写入接口

```python
def record_flow_transition(event: FlowTransitionEvent) -> None:
    """Record to Episodic Memory. Implementation in later change."""
    pass  # stub，RunController 在升降级时调用
```

---

## 7. 迁移路径

1. **Phase 1**：domain 类型 + flow_engine/graphs 定义。
2. **Phase 2**：FlowEngine、FlowMapper、flow_mapping.yaml。
3. **Phase 3**：GateInput/Verdict 扩展，GateService 升降级与 backtrack 逻辑。
4. **Phase 4**：RunController 集成，按图驱动，处理升降级与回退。
5. **Phase 5**：配置、回归测试、record_flow_transition stub。

---

## 8. 依赖关系

```
domain/models
  ├── flow_engine/{graphs, engine, mapper}
  ├── gate_service（扩展）
  └── run_controller（使用 FlowEngine）
```

Conductor 通过 FlowMapper 间接依赖，不依赖 RunController 或 GateService。
