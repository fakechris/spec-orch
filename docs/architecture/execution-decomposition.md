# Execution Decomposition

> Status: current-state decomposition document, not a target design
> Date: 2026-03-29

## Purpose

这份文档只回答一个问题：

**spec-orch 当前的执行层到底是怎么分裂出来的，以及它和七层叙事、NLAH/IHR 论文对象分别怎么对应。**

它不做以下事情：

- 不决定是否把 `issue` 和 `Mission` 收敛到一条 spine
- 不决定新的目录结构
- 不提出新的统一抽象名称

它的作用是先把细节拆开，避免后面在高层语义上“把不同东西当成同一个东西”。

## Scope

本文聚焦三组对象：

1. 当前执行层对象
   - `RunController`
   - `WorkerHandle`
   - `PacketExecutor`
   - `RoundOrchestrator`
   - `MissionLifecycleManager`
2. 七层叙事中的 `Task / Harness / Execution / Evidence / Control`
3. NLAH/IHR 论文中的对象
   - contracts
   - roles
   - stage structure
   - adapters & scripts
   - state semantics
   - failure taxonomy
   - runtime charter

主要代码锚点：

- [`src/spec_orch/services/run_controller.py`](../../src/spec_orch/services/run_controller.py)
- [`src/spec_orch/services/packet_executor.py`](../../src/spec_orch/services/packet_executor.py)
- [`src/spec_orch/services/round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py)
- [`src/spec_orch/services/mission_execution_service.py`](../../src/spec_orch/services/mission_execution_service.py)
- [`src/spec_orch/services/lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py)
- [`src/spec_orch/services/workers/oneshot_worker_handle.py`](../../src/spec_orch/services/workers/oneshot_worker_handle.py)
- [`src/spec_orch/services/workers/acpx_worker_handle.py`](../../src/spec_orch/services/workers/acpx_worker_handle.py)
- [`src/spec_orch/domain/models.py`](../../src/spec_orch/domain/models.py)

## Executive Summary

当前执行层不是一个统一 runtime core，而是三种“叶子执行”形态并存：

1. `issue` 叶子执行
   - 主控：`RunController`
   - 语义：单个 issue 的完整闭环
   - 闭环位置：叶子自己闭环

2. `Mission` supervised 叶子执行
   - 主控：`RoundOrchestrator` + `WorkerHandle`
   - 语义：单个 `WorkPacket` 先产出结果，再由 round supervisor 决策
   - 闭环位置：round 层闭环

3. `Mission` parallel packet 叶子执行
   - 主控：`ParallelRunController` + `PacketExecutor`
   - 语义：对 packet 直接跑 build 或 build+verify
   - 闭环位置：plan / wave 结果聚合层

因此，下面这句话在今天的代码里是**不成立**的：

> “Mission 最终落到单个 packet 时，就是调用同一个单 issue 流。”

更准确的说法是：

> `Mission` 和 `issue` 在更高抽象上都属于“执行单元”，但它们当前并不共享同一个闭环 owner，也不共享同一种状态语义。

## 1. 当前执行层拆解

### 1.1 issue spine: 单个 issue 的完整闭环

`issue` spine 的主语是 [`Issue`](../../src/spec_orch/domain/models.py)。

其核心执行路径由 [`RunController.run_issue()`](../../src/spec_orch/services/run_controller.py) 驱动，包含：

- load issue
- resolve flow
- prepare workspace
- create `run_id`
- write initial artifacts
- spec snapshot / approval gate
- builder
- verification
- review initialization
- gate evaluation
- run-level persistence

这里的关键点不是“调了一次 builder”，而是：

**一个 issue 自己完成了从契约冻结到执行、验证、门控的完整 run 闭环。**

它的主要状态载体是：

- `RunState`
- `spec_snapshot.json`
- `progress.json`
- `report.json`
- `run_artifact/live.json`

这条链可以概括为：

```text
Issue -> Run -> Build -> Verify -> Review -> Gate -> Persist
```

### 1.2 Mission supervised spine: packet 先执行，round 再闭环

`Mission` supervised 路径的主语不是 `Issue`，而是：

- [`Mission`](../../src/spec_orch/domain/models.py)
- [`ExecutionPlan`](../../src/spec_orch/domain/models.py)
- [`Wave`](../../src/spec_orch/domain/models.py)
- [`WorkPacket`](../../src/spec_orch/domain/models.py)
- [`RoundSummary` / `RoundDecision`](../../src/spec_orch/domain/models.py)

其核心执行路径由 [`RoundOrchestrator.run_supervised()`](../../src/spec_orch/services/round_orchestrator.py) 驱动。

一轮 round 的逻辑是：

```text
Wave -> dispatch packet workers -> collect artifacts -> supervisor review
     -> acceptance / visual / gate evidence -> continue / retry / replan / ask_human
```

当它落到单个 `WorkPacket` 时，真正发生的是：

1. 生成 `session_id = mission-<mission_id>-<packet_id>`
2. 创建或复用 `WorkerHandle`
3. 生成 worker prompt
4. 调 `handle.send(...)`
5. 收集 `BuilderResult`

然后**不会**立刻像 `RunController` 那样在 packet 本身里完成整个闭环。

后续动作被提升到了 round 层：

- collect manifest paths
- packet-level verification
- packet-level gate verdict
- visual evaluation
- acceptance evaluation
- supervisor 决策
- plan patch
- session ops（spawn / cancel）

所以它的结构是：

```text
Mission -> Plan -> Wave -> Packet Execute -> Round Collect -> Round Decide
```

这条链的闭环 owner 是 `RoundOrchestrator`，不是 packet 自己。

### 1.3 Mission parallel spine: packet executor 的中间态

`run-plan` 这条路不是 `RunController`，也不是 `RoundOrchestrator`。

它主要走：

- [`ParallelRunController`](../../src/spec_orch/services/parallel_run_controller.py)
- [`WaveExecutor`](../../src/spec_orch/services/wave_executor.py)
- [`PacketExecutor`](../../src/spec_orch/services/packet_executor.py)

这里的 `PacketExecutor` 有两种形态：

1. `SubprocessPacketExecutor`
   - 只负责 `codex exec`
2. `FullPipelinePacketExecutor`
   - 负责 `build -> verify`

注意这里虽然名字里有 “full pipeline”，但它依然**不是** `RunController` 的完整 issue 闭环，因为缺少：

- spec snapshot / approval
- review initialization
- run-level gate/report 生命周期
- acceptance / explain / issue-level state transition

所以这一层更像：

```text
Packet -> build(+verify) -> packet result
```

它是“比纯 worker 更厚、比 issue run 更薄”的中间态。

## 2. 为什么 Mission 的单 packet 不等于 issue 的单 run

### 2.1 直接差异

| 对比项 | issue run | Mission packet |
|---|---|---|
| 主语 | `Issue` | `WorkPacket` |
| owner | `RunController` | `WorkerHandle` + `RoundOrchestrator` |
| 目标 | 把这一张票跑到 gate 可判断 | 为本轮 supervisor 提供一个局部结果 |
| 闭环位置 | 叶子执行单元自己闭环 | round 层统一闭环 |
| 状态 | `RunState` | `RoundStatus` + `RoundDecision` + session ops |
| 会话语义 | file-backed continuity 为主 | `session_id` 真正一等 |
| 失败后的下一步 | rerun / review / accept / gate reconsider | retry / replan_remaining / ask_human / stop |

### 2.2 架构上的原因

这不是纯粹的历史偶然，也有结构上的必然。

Mission 要支持：

- wave 并行
- packet 粒度的 session 复用
- round 粒度的汇总与监督
- plan patch
- 多 packet 的统一验收和视觉/浏览器证据

为了做到这些，packet 本身必须保持足够轻，不能天然携带整套 issue run 的闭环语义。

换句话说：

- `issue` 适合 `leaf-owned closure`
- `Mission` 适合 `round-owned closure`

### 2.3 历史上的原因

当前差异也明显带有“分头长出来”的痕迹。

今天的代码不是从同一个 runtime core 抽象出来的，而是：

- issue 这条线先长成 `RunController`
- plan/wave 这条线又长出 `PacketExecutor`
- mission supervision 这条线再长出 `WorkerHandle` + `RoundOrchestrator`

所以现在并不是一个统一对象在不同层复用，而是三个相似但不等价的执行 owner 并存。

## 3. 放回七层叙事之后，它们分别在哪里

### 3.1 issue spine 在七层中的落点

| 平面 | issue spine 中的主要对象 |
|---|---|
| Contract | `Issue`、`spec_snapshot.json`、spec approval |
| Task | `FlowType`、flow graph steps |
| Harness | builder preamble、verification config、gate policy、context assembly |
| Execution | `RunController`、builder adapter、workspace |
| Evidence | verification、review、gate、report、artifact manifest |
| Control | CLI `run-issue/review-issue/accept-issue/status`、daemon single-issue path |
| Evolution | run artifacts 被后续 analyzer/evolver 消费 |

issue spine 的特点是：

- 七层基本都能在一条链上看到
- 但几乎都被 `RunController` 串在一起

### 3.2 Mission supervised spine 在七层中的落点

| 平面 | Mission supervised spine 中的主要对象 |
|---|---|
| Contract | `Mission`、`spec.md`、mission acceptance criteria |
| Task | `ExecutionPlan`、`Wave`、`WorkPacket` |
| Harness | worker prompt construction、supervisor context assembly、session ops |
| Execution | `WorkerHandle.send()`、packet workspace、ACPX/one-shot worker |
| Evidence | `round_summary.json`、`round_decision.json`、verification outputs、gate verdicts、visual/acceptance review |
| Control | `MissionLifecycleManager`、dashboard launcher、daemon mission path |
| Evolution | round and mission artifacts 被 analyzer/evolver 消费 |

Mission spine 的特点是：

- `Task` 平面更强
- `Control` 更强
- `Execution` 自身更薄
- 闭环被抬升到 `Evidence + Control`

### 3.3 关键判断

七层并没有错，但它容易掩盖一个事实：

**同样叫 Execution Plane，issue 和 Mission 里面装的并不是同一种执行 owner。**

所以如果只看七层框图，很容易误以为：

- `WorkPacket` 最终调用的就是和 `Issue` 一样的执行闭环

而当前代码并不是这样。

## 4. 放回 NLAH / IHR 论文对象之后，它们分别对应什么

这一节不是说 spec-orch 已经实现了 NLAH，而是把当前对象映射到论文对象上，看看哪里已经有对应物，哪里还只是碎片。

### 4.1 Contracts

当前对应物：

- `Mission.spec.md`
- `Issue.acceptance_criteria`
- `spec_snapshot.json`
- `gate.policy.yaml`
- `TaskContract`

现状判断：

- contracts 已经存在
- 但分散在 mission spec、issue snapshot、gate policy、verification config 里
- 还不是一个统一、可执行、可搬运的 harness contract object

### 4.2 Roles

当前对应物：

- builder
- reviewer
- supervisor
- acceptance evaluator
- visual evaluator
- worker

现状判断：

- roles 已经隐含存在
- 但大多散落在 adapter、service、prompt preamble 和命令入口里
- role boundary 还没有显式写成 runtime contract

### 4.3 Stage Structure

当前对应物：

- issue 路径：`spec -> build -> verify -> review -> gate`
- mission 路径：`plan -> wave -> round collect -> decide -> continue/retry/replan`

现状判断：

- stage structure 是当前代码里最真实的对象之一
- 但 issue 和 Mission 各自有一套 stage structure
- 还没有被收敛成共享语义

### 4.4 Adapters & Scripts

当前对应物：

- builder adapters
- `PacketExecutor`
- verification commands
- browser evidence collector
- visual evaluator
- acceptance evaluator

现状判断：

- 这一块已经非常强
- 是最接近论文里 `Adapters & Scripts` 的部分
- 但仍然是 service + adapter 族，不是 harness 文本的一部分

### 4.5 State Semantics

当前对应物：

- issue path: `progress.json` / `report.json` / `run_artifact/live.json`
- mission path: `round_summary.json` / `round_decision.json` / worker `session_id`
- shared: artifact manifests / telemetry / spec snapshot

现状判断：

- state semantics 已经存在，但被分成 run state、mission phase、round state、session state、artifact state
- 也就是说“有状态语义”，但没有一个统一 state model

### 4.6 Failure Taxonomy

当前对应物：

- `RunState.FAILED`
- gate failed conditions
- `RoundAction.RETRY / ASK_HUMAN / STOP / REPLAN_REMAINING`
- fallback events

现状判断：

- failure handling 很多
- failure taxonomy 不统一
- 有现象级处理，没有统一命名体系

### 4.7 Runtime Charter

当前最接近的东西是：

- gate policy
- compliance rules
- builder preambles
- flow routing / flow engine
- mission supervision rules

现状判断：

- 当前没有单一 runtime charter 对象
- 运行时行为规则散在 flow、policy、adapter、supervisor、acceptance 几个子系统里

## 5. 这一拆解对术语收口意味着什么

### 5.1 `Issue` 和 `Mission` 在高抽象上是不是“一个东西”

如果抽到足够高层，它们可以被看成同一族对象：

- 都承载契约
- 都最终进入执行
- 都需要证据
- 都可能被控制面恢复、重试、回放

但在今天的代码里，它们**不是同一个 runtime object**。

更准确的说法是：

- `Mission` 是 contract/program object
- `Issue` 是 run/input object
- `WorkPacket` 是 mission-derived execution unit

### 5.2 哪一层最适合去找“共同语义”

不是在 `Issue` 和 `Mission` 名字本身上找共同语义，而是往下找：

- execution unit
- execution attempt
- execution evidence
- supervision loop

今天真正分裂的，不是“我们有没有执行”，而是：

- 谁拥有这次执行
- 谁对这次执行结果做闭环
- 谁持有可恢复的连续性

### 5.3 当前最稳的结论

在不做任何重构结论的前提下，当前最稳的判断是：

1. `issue` 和 `Mission` 不是简单上下位关系
2. `Mission` 的单 packet 不等于 `issue` 的单 run
3. 两者在更高层可被视为同一执行语义族，但当前还没有共享 runtime owner
4. 七层叙事能描述它们的共同目标，但不能替代它们当前真实的对象边界
5. 论文里的 NLAH 对象在 spec-orch 中大多都能找到碎片对应物，但还没有被收成一个统一 harness object

## 6. 下一步文档工作

在这份拆解之后，下一步更适合继续写的不是新架构，而是术语和对象边界。

建议顺序：

1. 继续扩充 glossary
   - `ExecutionUnit`
   - `ExecutionAttempt`
   - `Supervisor`
   - `Worker`
   - `PlanPatch`
2. 再写一份 object-boundary doc
   - 哪些对象是 contract-layer
   - 哪些对象是 execution-layer
   - 哪些对象只是 persistence carrier
3. 最后再进入 spine 收敛或 package realignment

这一步的重点不是“先统一”，而是先确认：

**哪些东西本来就应该相同，哪些东西只是名字相似。**
