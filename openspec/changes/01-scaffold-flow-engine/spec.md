# Spec: 骨架流程引擎

> **Change**: 01-scaffold-flow-engine  
> **格式**: Requirement + Scenario (Given/When/Then)

---

## REQ-1: FlowType 与 FlowGraph 定义

**REQ-1.1** 系统应定义 `FlowType` 枚举，包含 `Full`、`Standard`、`Hotfix` 三种取值。

**REQ-1.2** 系统应定义 `FlowGraph` 为有向无环图，包含：步骤序列（`FlowStep`）、步骤间转换条件、可跳过条件、回退路径（backtrack）。

**REQ-1.3** 每种 FlowType 对应一个预定义的 FlowGraph，与 change-management-policy 的步骤表一致。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S1.1 | FlowType 为 Full | 查询 FlowGraph | 返回包含 discuss, freeze, plan, promote, execute, verify, gate, pr, merge, retro 的步骤序列 |
| S1.2 | FlowType 为 Standard | 查询 FlowGraph | 返回包含 create_issue, create_branch, implement, verify, gate, pr, merge 的步骤序列，不包含 discuss/freeze/plan/promote/retro |
| S1.3 | FlowType 为 Hotfix | 查询 FlowGraph | 返回与 Standard 类似的步骤，但 gate 使用 minimal profile，pre_merge_review 为可选 |

---

## REQ-2: 步骤可跳过条件

**REQ-2.1** 每个步骤可标注 `skippable_if` 条件；当条件满足时，该步骤可被跳过而不阻塞流程。

**REQ-2.2** 可跳过条件应可配置（如 `doc_only` 跳过 verify 中的 test 子步骤），默认无跳过。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S2.1 | 步骤 verify 配置了 skippable_if: doc_only | 变更被标记为 doc_only | 系统允许跳过 verify 或仅执行其子集 |
| S2.2 | 步骤无 skippable_if | 任意变更 | 步骤不可跳过 |

---

## REQ-3: Gate 触发的流程升级

**REQ-3.1** Gate 在 evaluate 时，若发现「声称流程与实际改动不符」（如声称 doc-only 但改了代码），应产出 `promotion_required` 信号。

**REQ-3.2** GateVerdict 应包含可选字段 `promotion_required: bool` 和 `promotion_target: FlowType | None`。

**REQ-3.3** RunController 收到 `promotion_required=True` 时，应终止当前流程，切换到 `promotion_target` 流程并从其起点重新开始。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S3.1 | 当前流程为 Standard，issue 声称 doc-only | Gate 检测到代码文件被修改 | GateVerdict.promotion_required=True, promotion_target=Standard（或 Full，依策略） |
| S3.2 | RunController 收到 promotion_required | 执行流程推进 | 切换到新流程起点，记录 FlowTransitionEvent |

---

## REQ-4: Conductor 建议 + Gate 确认的流程降级

**REQ-4.1** Conductor 可根据 Intent 和上下文建议降级（如 Feature 范围小 → Standard）；建议存储在 issue 元数据或 ConductorState 中。

**REQ-4.2** Gate 在 evaluate 时，若满足降级条件（如改动量在阈值内），可产出 `demotion_suggested` 信号；仅当 Conductor 已建议且 Gate 确认时，降级才生效。

**REQ-4.3** 降级事件应记录到 Episodic Memory（通过定义的写入接口）。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S4.1 | 当前流程为 Full，Conductor 建议降级到 Standard | Gate 确认改动量在阈值内 | GateVerdict.demotion_suggested=True, demotion_target=Standard |
| S4.2 | RunController 收到 demotion_suggested 且 Conductor 已建议 | 执行流程推进 | 切换到 demotion_target 流程，记录 FlowTransitionEvent |
| S4.3 | Conductor 未建议降级 | Gate 产出 demotion_suggested | RunController 不执行降级（或仅记录供后续分析） |

---

## REQ-5: Intent → Flow 可配置映射

**REQ-5.1** 系统应支持通过配置文件（如 YAML）定义 IntentCategory 到 FlowType 的映射规则。

**REQ-5.2** 映射应支持默认规则与覆盖规则（如 Linear 标签 `hotfix` 覆盖 Intent 映射）。

**REQ-5.3** 未配置的 IntentCategory（如 Exploration、Question）应映射为「不进入流程」或显式 None。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S5.1 | 配置为 Feature→Full, Bug→Standard, Quick_Fix→Standard | Intent=Feature | resolve_flow_type 返回 Full |
| S5.2 | 配置同上，issue 带 hotfix 标签 | 解析 flow | 返回 Hotfix，覆盖 Intent 映射 |
| S5.3 | Intent=Exploration | 解析 flow | 返回 None 或特殊值表示不进入流程 |

---

## REQ-6: 回退路径

**REQ-6.1** Gate 判定失败时，应分类失败原因为：`recoverable`、`needs_redesign`、`promotion_required`。

**REQ-6.2** `recoverable`：回到 Execute 阶段重试。`needs_redesign`：回到 Spec/Plan 阶段。`promotion_required`：流程升级后从新流程起点开始。

**REQ-6.3** FlowGraph 应定义每个步骤的回退目标（backtrack 边）。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S6.1 | Gate 失败，原因=recoverable | RunController 处理 | 回退到 execute 步骤 |
| S6.2 | Gate 失败，原因=needs_redesign | RunController 处理 | 回退到 spec_drafting 或 plan 步骤 |
| S6.3 | Gate 失败，原因=promotion_required | RunController 处理 | 执行 REQ-3 的升级逻辑 |

---

## REQ-7: 升降级失败处理

**REQ-7.1** 若 promotion/demotion 目标流程不存在或配置错误，系统应记录错误并保持当前流程，不静默失败。

**REQ-7.2** 若 Gate 产出 promotion_required 但 promotion_target 为当前或更低流程，应视为配置错误，记录并告警。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S7.1 | promotion_target 指向不存在的 FlowType | RunController 执行切换 | 记录错误，保持当前流程，返回明确错误信息 |
| S7.2 | promotion_target=Standard，当前=Full | RunController 执行切换 | 视为无效，记录告警，不降级 |

---

## REQ-8: 兼容性

**REQ-8.1** 未指定 flow 且无 Intent/标签时，系统应默认使用 Standard 流程，行为与当前 RunController 的隐式流程等价。

**REQ-8.2** 现有 RunController 的 `run_issue`、`advance` 等公开接口签名保持不变；仅内部实现改为按 FlowGraph 驱动。

**REQ-8.3** 现有测试（回归测试）应全部通过，无需修改测试用例（除明确覆盖新行为的用例外）。

| Scenario | Given | When | Then |
|----------|-------|------|------|
| S8.1 | 无 flow 指定、无 Intent | 调用 run_issue | 使用 Standard 流程，执行路径与当前实现等价 |
| S8.2 | 现有集成测试 | 运行全量测试 | 全部通过 |
