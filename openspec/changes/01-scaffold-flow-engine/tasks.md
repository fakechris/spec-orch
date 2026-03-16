# Tasks: 骨架流程引擎

> **Change**: 01-scaffold-flow-engine  
> **格式**: 可执行 checklist，含验证方式、依赖标记、并行指示

---

## Phase 1: 领域模型与图定义

| ID | 任务 | 验证方式 | 依赖 | 并行 |
|----|------|---------|------|------|
| T1.1 | 在 `domain/models.py` 新增 `FlowType` 枚举 | `pytest -k FlowType` | — | — |
| T1.2 | 新增 `FlowStep`、`FlowGraph`、`FlowTransition` 数据类 | 单元测试构造实例 | T1.1 | 可与 T1.1 同批 |
| T1.3 | 新增 `FlowTransitionEvent`、扩展 `GateVerdict` | 单元测试 | T1.2 | — |
| T1.4 | 创建 `flow_engine/graphs.py`，定义 Full 流程的 FlowGraph | 断言 steps/transitions/backtrack 与 change-management-policy 一致 | T1.2 | — |
| T1.5 | 定义 Standard 流程的 FlowGraph | 同上 | T1.4 | 可与 T1.4 串行 |
| T1.6 | 定义 Hotfix 流程的 FlowGraph | 同上 | T1.5 | 可与 T1.5 串行 |

---

## Phase 2: FlowEngine 与 FlowMapper

| ID | 任务 | 验证方式 | 依赖 | 并行 |
|----|------|---------|------|------|
| T2.1 | 实现 `FlowEngine.get_graph(flow_type) -> FlowGraph` | 单元测试三种 flow 均返回正确图 | T1.6 | — |
| T2.2 | 实现 `FlowEngine.get_next_steps(step_id) -> list[str]` | 单元测试 | T2.1 | — |
| T2.3 | 实现 `FlowEngine.get_backtrack_target(step_id, reason) -> str | None` | 单元测试 recoverable/needs_redesign/promotion_required | T2.1 | 可与 T2.2 并行 |
| T2.4 | 创建 `flow_mapping.yaml` 默认配置（Intent→Flow） | 配置文件可加载 | — | 可与 T2.1 并行 |
| T2.5 | 实现 `FlowMapper.resolve_flow_type(intent, issue_metadata) -> FlowType | None` | 单元测试覆盖 Feature→Full, Bug→Standard, hotfix 标签覆盖 | T2.4 | T2.4 |
| T2.6 | 实现步骤 skippable_if 的检查逻辑 | 单元测试 doc_only 等条件 | T2.1 | 可与 T2.3 并行 |

---

## Phase 3: Gate 扩展

| ID | 任务 | 验证方式 | 依赖 | 并行 |
|----|------|---------|------|------|
| T3.1 | 扩展 `GateInput`：claimed_flow, demotion_proposed_by_conductor, diff_stats | 单元测试 | T1.1 | — |
| T3.2 | GateService.evaluate 在 mergeable=False 时设置 backtrack_reason | 单元测试 failed_conditions → reason 映射 | T1.3 | — |
| T3.3 | GateService.evaluate 实现 promotion_required 逻辑（简化版：claimed doc-only 但 verification 涉及代码） | 单元测试 | T3.1 | T3.2 |
| T3.4 | GateService.evaluate 实现 demotion_suggested 逻辑（Conductor 建议 + 改动量阈值） | 单元测试 | T3.1 | T3.3 |

---

## Phase 4: RunController 集成

| ID | 任务 | 验证方式 | 依赖 | 并行 |
|----|------|---------|------|------|
| T4.1 | RunController 注入 FlowEngine、FlowMapper | 构造 RunController 时传入，默认使用内置实例 | T2.5 | — |
| T4.2 | 实现 `_resolve_flow(issue) -> FlowType`，默认 Standard | 单元测试无指定时返回 Standard | T4.1 | — |
| T4.3 | run_issue 按 FlowGraph 选择初始步骤 | 集成测试：Full 从 discuss 开始，Standard 从 implement 开始 | T4.2, T2.1 | — |
| T4.4 | 步骤推进逻辑改为基于 FlowEngine.get_next_steps | 回归测试现有 advance 行为 | T4.3 | — |
| T4.5 | 处理 GateVerdict.promotion_required：切换流程、记录 FlowTransitionEvent | 集成测试 | T3.3, T4.4 | — |
| T4.6 | 处理 GateVerdict.demotion_suggested：切换流程、记录事件 | 集成测试 | T3.4, T4.5 | — |
| T4.7 | 处理 backtrack_reason：回退到对应步骤 | 集成测试 | T3.2, T4.4 | — |

---

## Phase 5: 配置、接口与回归

| ID | 任务 | 验证方式 | 依赖 | 并行 |
|----|------|---------|------|------|
| T5.1 | 定义 `record_flow_transition(event)` 接口（stub 实现） | 调用不抛错，可被 mock | T1.3 | — |
| T5.2 | RunController 在升降级时调用 record_flow_transition | 单元测试 mock 验证调用 | T4.5, T4.6 | — |
| T5.3 | CLI 增加 `--flow` 可选参数 | `spec-orch run --flow hotfix` 生效 | T4.2 | — |
| T5.4 | 全量回归测试 | `pytest` 全部通过 | T4.7 | — |
| T5.5 | 更新 change-management-policy 或架构文档中的「实现状态」 | 文档 review | T5.4 | — |

---

## 并行执行建议

```
Phase 1:  T1.1 ─┬─ T1.2 ─ T1.3
                └─ T1.4 ─ T1.5 ─ T1.6

Phase 2:  T2.4 ─ T2.5     T2.1 ─ T2.2
                          T2.1 ─ T2.3
                          T2.1 ─ T2.6

Phase 3:  T3.1 ─┬─ T3.2
                └─ T3.3 ─ T3.4

Phase 4:  T4.1 ─ T4.2 ─ T4.3 ─ T4.4 ─┬─ T4.5
                                      ├─ T4.6
                                      └─ T4.7

Phase 5:  T5.1 ─ T5.2   T5.3   T5.4 ─ T5.5
```

---

## 验收标准

- [ ] 三种 FlowType 均有完整 FlowGraph 定义
- [ ] Intent→Flow 映射可通过 YAML 配置
- [ ] Gate 能产出 promotion_required、demotion_suggested、backtrack_reason
- [ ] RunController 能响应升降级与回退
- [ ] 默认行为与当前实现等价，回归测试通过
- [ ] FlowTransitionEvent 写入接口已定义并调用
