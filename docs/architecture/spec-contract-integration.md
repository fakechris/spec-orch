# Spec 层级整合：OpenSpec + Agent-Spec Contract 在 spec-orch 中的位置

> 日期: 2026-03-16
> 来源: T3.3 gate promotion_required 实验（PR #42）
> 前置: orchestration-brain-design.md, change-management-policy.md

## 一、实验发现

### 1.1 三层 spec 各自解决什么问题

通过在 T3.3 上做完整的 OpenSpec → Contract → Execute 链路，发现 spec
实际上存在三个不同粒度的层次，各自解决不同问题：

| 层次 | 文档 | 回答的问题 | 消费者 |
|------|------|-----------|--------|
| **L1: OpenSpec Spec** | `spec.md` | 做什么？什么行为必须成立？ | 人类 review、Gate 验收 |
| **L2: Agent-Spec Contract** | `contract.md` | 怎么安全地做？改什么、不改什么？ | Coding agent |
| **L3: 测试** | `test_*.py` | 做完了吗？行为成立吗？ | CI、Gate |

关键洞察：**L1 和 L2 不是重复，而是面向不同消费者的翻译。**

- L1 (Spec) 面向人和验收：定义外部行为约束，不关心改哪个文件。
- L2 (Contract) 面向 coding agent：定义执行边界、禁止路径、失败排查方案。
- L3 (Test) 面向 CI：L1 的机器可执行版本。

### 1.2 实验中的关键证据

| 证据 | 解释 |
|------|------|
| Contract 中"claimed_flow 用 str 不用枚举"阻止了跨 task 耦合 | L1 Spec 没有也不应该关心这个——它是实现层面的边界约束 |
| Contract 中"promotion 不影响 mergeable"是设计决定，不是 spec 推导 | Spec 留了这个空间，contract 做了显式选择 |
| Forbidden Paths 比 Allowed Paths 长 | 对 agent 来说，"不做什么"比"做什么"更重要 |
| 执行时 0 次返工 | 因为 contract 提前消除了歧义，agent 无需做决策 |

### 1.3 什么情况下不需要 contract

| 特征 | 需要 contract | 不需要 |
|------|---------------|--------|
| 修改核心路径（Gate, RunController, Conductor） | Yes | — |
| 新增独立模块（新文件、新 evolver） | — | Yes |
| Forbidden Paths > Allowed Paths | Yes | — |
| 改动可能破坏现有测试 | Yes | — |
| 纯文档/配置 | — | Yes |
| 涉及多个 task 的边界协调 | Yes | — |

**经验法则：如果一个 task 的回归风险大于实现复杂度，就写 contract。**

## 二、流程整合方案

### 2.1 在三种流程中的位置

```
Full 流程:
  Issue → Discuss → Spec → Plan → [Contract?] → Execute → Verify → Gate → PR → Merge → Retro
                     L1          L2             L3

Standard 流程:
  Issue → [Contract?] → Implement → Verify → Gate → PR → Merge
           L2                        L3

Hotfix 流程:
  Issue → Fix → Minimal-Gate → Merge → Post-Review
  (不写 contract)
```

### 2.2 Contract 生成规则

| 流程 | Contract 策略 |
|------|--------------|
| **Full** | Plan 阶段按 task 逐个评估：高风险 task 写 contract，低风险 task 跳过 |
| **Standard** | Conductor 判定 intent 后，如果涉及核心路径 → 自动生成 contract 骨架 |
| **Hotfix** | 不写 contract，事后 Post-Review 补充 |

### 2.3 谁生成 contract

Contract 不需要人写。基于 T3.3 的实验，contract 的结构是高度模板化的：

1. **Intent** — 从 spec requirement 提取
2. **Decisions** — 从 design.md 提取 + 依赖分析推导
3. **Boundaries** — 从 task dependencies + `git log` 推导：
   - Allowed: task 声明的文件
   - Forbidden: 同 change 其他 task 声明的文件
4. **Completion Criteria** — 从 spec scenarios 提取
5. **Verification Plan** — 从 pyproject.toml 的 test/lint 配置生成
6. **Risk Notes** — 从代码静态分析（import graph、修改文件的被引用次数）推导

**这就是 Conductor 的一个 Skill：`generate-task-contract`。**

### 2.4 与骨架/肌肉架构的映射

```
骨架层 (Scaffold):
  Full 流程的步骤序列现在变为：
    ... → plan → [contract_generation] → execute → verify → gate → ...
                  ^^^^^^^^^^^^^^^^
                  新步骤，skippable_if: task.risk_level == "low"

肌肉层 (Muscle):
  contract_generation 步骤的内部逻辑:
    - LLM 读 spec + design + task 依赖关系
    - 生成 contract 草稿
    - 按模板结构化输出
    - 可进化：ContractEvolver 从"contract 是否阻止了越界"学习
```

## 三、Contract 与现有概念的关系

### 3.1 与 compliance.contracts.yaml 的区别

| 维度 | compliance.contracts.yaml | agent-spec contract |
|------|--------------------------|---------------------|
| 粒度 | 全局规则（所有 run 共用） | 单 task 级别 |
| 检查时机 | builder 运行时实时检查 | 执行前约束 + 执行后验收 |
| 示例 | "builder 必须在首个 action 前叙述" | "本 task 不得修改 RunController" |
| 进化 | HarnessSynthesizer 从失败模式生成 | ContractEvolver 从越界事件生成 |

两者互补，不冲突。compliance 是运行时守卫，contract 是执行前围栏。

### 3.2 与 Gate 的关系

Gate 在 contract 流程中的角色不变——它仍然是终极仲裁者。但 Gate 多了一个
新的输入维度：**contract compliance**。

```
GateInput 可扩展:
  contract_violations: list[str]  # agent 执行中违反 contract 的记录
```

如果 agent 改了 Forbidden Paths 中的文件，Gate 可以拒绝。
这与 promotion_required 类似——信号式设计，Gate 决定是否 block。

### 3.3 与 Conductor 的关系

Conductor 在 contract 流程中扮演两个角色：

1. **风险评估**：判断一个 task 是否需要 contract
   - 输入：task 描述、涉及文件列表、import graph
   - 输出：risk_level (low / medium / high)

2. **Contract 生成**：为 high-risk task 生成 contract
   - 输入：spec requirement、design decisions、task dependencies
   - 输出：结构化 contract 文档

这两个都是 Conductor 的 Skill，可以独立进化。

## 四、实施路径

### Phase 1: 手动验证（当前）

- 高风险 task 人工写 contract（如 T3.3）
- 执行后对照 contract 验收
- 积累 contract 样本（目标：10-15 个覆盖不同类型的 task）

### Phase 2: 半自动生成

- 基于积累的样本，实现 `spec-orch contract generate <task-id>`
- 人工 review contract 后交给 agent 执行
- Gate 增加 contract_violations 检查

### Phase 3: 全自动 + 进化

- Conductor 自动判断 risk_level
- 高风险 task 自动生成 contract
- ContractEvolver 从越界事件学习，改进生成质量
- 低风险 task 跳过 contract（step skippability）

## 五、不做什么

1. **不给每个 task 都写 contract** — 低风险 task 的 contract 开销 > 收益
2. **不让 contract 替代 spec** — contract 是 spec 的下游翻译，不是替代
3. **不让 contract 替代 test** — contract 定义预期，test 验证预期
4. **不发明新格式** — contract 就是 Markdown，遵循固定 section 结构
5. **不在 Hotfix 流程中引入 contract** — 速度优先
