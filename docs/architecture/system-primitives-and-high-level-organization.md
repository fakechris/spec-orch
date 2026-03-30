# System Primitives and High-Level Organization

> 日期: 2026-03-29
> 状态: 当前共识基线
> 目的: 在开工前，统一 spec-orch 的高层组织结构、共享原语、应独立的结构、以及应抽出的概念

---

## 1. 结论先行

spec-orch 接下来不应继续围绕“issue 路径 vs mission 路径”去堆局部实现，而应围绕一组共享原语和几个明确的独立结构来组织。

当前共识可以压成一句话：

> **不先强行合并 owner；先统一原语、显化 runtime seam、把 decision review loop 独立出来。**

这意味着：

- `Issue` 和 `Mission` 可以继续作为不同主语存在
- `RunController` 和 `RoundOrchestrator` 可以继续作为不同 owner 存在
- 但它们必须逐步共享同一套执行原语、证据原语、决策原语、memory 原语

---

## 2. 应独立出来的结构

下面这些不是“实现细节”，而是应该在程序组织上可见的独立结构。

### 2.1 Contract Core

职责：

- 管理任务契约、spec snapshot、acceptance criteria、约束、questions / decisions
- 作为 `Issue` / `Mission` / `ExecutionPlan` / `WorkPacket` 的契约来源

为什么必须独立：

- `spec-kit` 这类系统说明，spec lifecycle 和 runtime execution 不是一回事
- 当前代码里契约信息散落在 `spec.md`、`spec_snapshot.json`、`task.spec.md`、`plan.json`、`mission.json`
- 如果 Contract Core 不独立，后续所有 execution / review / memory 都会继续吃不同格式的“半结构化输入”

应包含：

- spec parsing / import
- snapshot / freeze / approval
- question / answer / decision 记录
- contract normalization

### 2.2 Runtime Core

职责：

- 提供统一的 execution semantic seam
- 把 shared semantics 变成代码中的显式包边界

为什么必须独立：

- 这是 `deepagents` 最值得借鉴的部分：runtime assembly seam 必须可见
- 如果没有 Runtime Core，shared semantics 只会停留在文档和 reader/writer 层
- 现在 `RunController`、`PacketExecutor`、`WorkerHandle`、`RoundOrchestrator` 各自拼装执行事实，结构上不可控

应包含：

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- continuity abstraction
- normalized readers / writers

### 2.3 Supervision and Decision Core

职责：

- 管理 round review、decision points、human intervention、approval queue
- 把“谁可以决定什么”变成显式对象而不是 prompt 约定

为什么必须独立：

- 当前最缺的不是更多 memory，而是 decision review loop
- Mission 路径已经局部证明了这层的必要性：`RoundDecision`、`ask_human`、approval queue 都是真需求
- 这层如果继续散在 `RoundOrchestrator`、dashboard、telemetry、memory 里，后续无法做统一复盘和策略晋升

应包含：

- `SupervisionCycle`
- `DecisionPoint`
- `DecisionRecord`
- `DecisionReview`
- intervention / escalation model

### 2.4 Memory and Learning Core

职责：

- 管理 episodic / semantic / procedural learning
- 管理 distillation、recall、trend、failure patterns、success recipes

为什么必须独立：

- 这层现在已经存在，但承担的语义边界还不够清楚
- 需要明确它服务于 runtime 和 decision review，而不是替代 gate/policy/harness

应包含：

- file-backed memory provider
- optional semantic index
- derivation / distillation queue
- learning views
- policy promotion inputs

### 2.5 Evolution Core

职责：

- 把 memory / decision review / execution evidence 转化成 prompt/policy/skill/plan strategy 的系统改进

为什么必须独立：

- evolution 是系统级优化，不应嵌在单次 execution owner 里
- 当前 evolvers 已存在，但缺少与 Decision Review Loop 的显式耦合

应包含：

- evolver registry
- trigger policy
- promotion / review gates
- rollback / supersede semantics

### 2.6 Surfaces

职责：

- CLI
- daemon
- dashboard
- external APIs / Linear / GitHub / browser / ACPX

为什么必须独立：

- 它们是入口和展示层，不应承载核心对象语义
- 当前很多结构问题来自 shell 层直接塑造了 runtime 事实

---

## 3. 应抽出来的概念

下面这些概念应该从现有实现中抽出来，成为全系统统一语言。

### 3.1 执行语义

- `ExecutionUnit`
  - 一个最小可执行单元
  - `Issue` 和 `WorkPacket` 都可以映射到它

- `ExecutionAttempt`
  - 一次具体执行尝试
  - 是执行包络，不是结果，不是 round

- `ExecutionOutcome`
  - 一次尝试的结果
  - shared schema, different closure location

- `ArtifactRef`
  - 证据语义引用
  - 语义键稳定，文件名可变

- `Continuity`
  - 这次尝试如何持续
  - `file_backed_run` / `worker_session` / `oneshot_worker` / `subprocess_packet`

### 3.2 监督与决策语义

- `SupervisionCycle`
  - 上层监督循环
  - 不是 attempt

- `DecisionPoint`
  - 一个系统允许做出分支选择的位置
  - 必须能标注：规则决定 / LLM 决定 / 必须 ask human

- `DecisionRecord`
  - 当时上下文
  - 选择了什么
  - 为什么
  - 置信度
  - 是否升级

- `DecisionReview`
  - 人工复盘或自复盘的结果
  - 关注“这个点是否该继续自动化”

- `Intervention`
  - 对 `ask_human`、审批、跟进问题、人工 override 的统一建模

### 3.3 学习语义

- `MemoryEntry`
  - 基础 memory carrier

- `LearningView`
  - 面向具体节点注入的学习切片

- `Recipe`
  - 可复用成功模式

- `FailurePattern`
  - 可复用失败模式

- `PolicyAsset`
  - procedural memory / skill / constitution / gate rule / flow rule

### 3.4 契约语义

- `ContractSubject`
  - 契约作用的对象

- `ContractSnapshot`
  - 某时刻冻结的契约事实

- `AcceptanceContract`
  - 最终验收条件

- `ConstraintSet`
  - 范围、技术、权限、环境约束

---

## 4. 系统原语

下面这些原语应被视为全系统共享的最小语言，而不是某条 spine 的私有词。

### 4.1 Subject Primitives

- `Mission`
- `Issue`
- `ExecutionPlan`
- `Wave`
- `WorkPacket`

说明：

- 这些是系统的业务主语
- 不应被 service 名字替代
- `Mission` 和 `Issue` 不必合并，但都应能投影到 `ExecutionUnit`

### 4.2 Execution Primitives

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- `Continuity`

说明：

- 这是 issue spine 和 mission spine 首先应该共享的一组原语
- 重点是共享语义，不先共享 owner

### 4.3 Supervision Primitives

- `SupervisionCycle`
- `RoundDecision`
- `DecisionPoint`
- `DecisionRecord`
- `Intervention`

说明：

- `RoundDecision` 是现有对象
- `DecisionPoint` / `DecisionRecord` / `Intervention` 是需要补齐的原语

### 4.4 Learning Primitives

- `MemoryEntry`
- `LearningView`
- `FailurePattern`
- `SuccessRecipe`
- `EvolutionJournal`

说明：

- 这层负责“记住发生过什么”
- 不负责替代 gate / review / policy enforcement

### 4.5 Governance Primitives

- `Approval`
- `GateVerdict`
- `PolicyAsset`
- `Promotion`
- `Supersession`

说明：

- 这是系统治理层最小语言
- 负责“能不能放行”“能不能晋升为规则”“旧规则是否被替代”

---

## 5. 高层组织结构

下面是建议的 high-level 组织，不是目录草图，而是系统骨架。

```text
Contract Core
  -> produces ContractSubject / ContractSnapshot / AcceptanceContract

Runtime Core
  -> runs ExecutionUnit as ExecutionAttempt
  -> emits ExecutionOutcome + ArtifactRef

Supervision and Decision Core
  -> supervises attempts through SupervisionCycle
  -> emits RoundDecision / DecisionRecord / Intervention

Memory and Learning Core
  -> records episodic + semantic + procedural learnings
  -> exposes LearningView back into runtime

Evolution Core
  -> distills learnings into prompt / policy / skill / strategy improvements

Surfaces
  -> CLI / daemon / dashboard / external adapters
```

关键边界：

- Contract Core 决定“这件事是什么”
- Runtime Core 决定“这次怎么跑”
- Supervision Core 决定“跑完怎么判、是否继续、是否问人”
- Memory Core 决定“这次经验如何保留与召回”
- Evolution Core 决定“哪些经验要晋升成系统能力”
- Surfaces 只是入口与交互，不定义核心事实

---

## 6. 哪些东西不要再混

后续开工时，下面这些混淆要明确禁止。

### 6.1 不把 owner 当 object

不允许再把：

- `RunController`
- `RoundOrchestrator`
- `MissionLifecycleManager`

当成对象语义本身。

它们是 owner，不是系统原语。

### 6.2 不把 carrier 当 object

不允许再把：

- `report.json`
- `round_decision.json`
- `live.json`
- `manifest.json`

当成对象本体。

它们是 carrier，不是原语。

### 6.3 不把 round 当 execution attempt

- `Round` 是监督层
- `ExecutionAttempt` 是执行层

这条边界必须保持。

### 6.4 不把 memory 当 decision review

- memory 负责保留经验
- decision review 负责评估“这个决策过程是否合理、是否该继续自动化”

这两个层不能再混成一个“泛学习系统”

---

## 7. 与外部参考的整合结论

### 来自 deepagents 的启发

应吸收：

- 可见的 runtime assembly seam
- middleware / backend / state 的明确边界
- runtime core 必须是程序组织中的真实结构

不应照搬：

- LangGraph-specific runtime shape
- 它的工具和图执行假设

### 来自 spec-kit 的启发

应吸收：

- spec-first contract workflow
- command / template / preset 的分发方式
- constitution/spec/plan/tasks 的流程纪律

不应误用：

- 它不能替代 runtime core
- 它不能解决 dual-spine ownership

---

## 8. 开工前的最终判断

后续重构不应再被描述成“把 issue 和 mission 合并成一条线”。

更准确的目标是：

1. 先让两条 spine 共享同一套原语
2. 再让这些原语在代码组织里有独立结构
3. 再决定 owner 是否需要继续抽取或收敛

因此，接下来的实施顺序应理解为：

1. shared semantics
2. runtime core extraction
3. decision review loop extraction
4. contract / memory / evolution 的进一步收口

这四步中，前两步解决“程序组织”，第三步解决“系统学习与审计”，第四步才解决“长期演化能力”。

---

## 9. 最小共识

如果只保留最小共识，就是下面 8 条：

1. `Mission` 和 `Issue` 都保留，不强行合并
2. `ExecutionUnit` / `ExecutionAttempt` / `ExecutionOutcome` 是共享执行原语
3. `Round` 是 `SupervisionCycle`，不并入 attempt
4. `ArtifactRef` 是共享证据原语
5. `DecisionPoint` / `DecisionRecord` 必须补成一等原语
6. memory 不是 decision review 的替代物
7. runtime core 必须成为真实代码结构，而不是文档概念
8. shell / dashboard / daemon 不定义核心事实，只消费核心事实
