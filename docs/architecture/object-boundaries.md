# Object Boundaries

> Status: current-state object recovery document, not a target design
> Date: 2026-03-29

## Purpose

这份文档的目标不是发明新抽象，而是恢复当前代码里**已经存在的对象边界**。

它回答的是：

- 现在有哪些东西应当被当成一等对象来看
- 哪些只是执行 owner
- 哪些只是持久化载体
- 哪些只是 CLI / dashboard / adapter 壳

如果这一步不先做清楚，后面会持续出现两个问题：

1. 把 service 名称误当成领域对象
2. 把文件或 JSON 载体误当成 runtime object

## Scope

本文只做对象分类，不做重构决策。

主要代码锚点：

- [`src/spec_orch/domain/models.py`](../../src/spec_orch/domain/models.py)
- [`src/spec_orch/domain/protocols.py`](../../src/spec_orch/domain/protocols.py)
- [`src/spec_orch/services/run_controller.py`](../../src/spec_orch/services/run_controller.py)
- [`src/spec_orch/services/lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py)
- [`src/spec_orch/services/mission_service.py`](../../src/spec_orch/services/mission_service.py)
- [`src/spec_orch/services/round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py)
- [`src/spec_orch/services/run_artifact_service.py`](../../src/spec_orch/services/run_artifact_service.py)

## Executive Summary

当前代码里的对象边界，大致可以分成五类：

1. **Contract Objects**
   - 描述“要交付什么”
2. **Execution Objects**
   - 描述“要跑什么 / 正在跑什么”
3. **Supervision / Decision Objects**
   - 描述“谁在看结果并决定下一步”
4. **Persistence Carriers**
   - 只是把状态和证据落到文件里
5. **Shells / Adapters / Services**
   - 负责接入、调度、搬运、桥接，不等于领域对象本身

当前最大的问题不是“对象完全没有”，而是：

- 一等对象和 service 名字混在一起
- runtime owner 和 persistence carrier 混在一起
- 高层语义和执行壳混在一起

## 1. 一等对象：当前最应该被当成对象看的东西

### 1.1 Contract Objects

这些对象回答“我们要交付什么”。

| 对象 | 当前代码锚点 | 说明 |
|---|---|---|
| `Mission` | [`models.py`](../../src/spec_orch/domain/models.py) | 跨 issue 的契约对象 |
| `Issue` | [`models.py`](../../src/spec_orch/domain/models.py) | 单次 issue 输入对象 |
| `SpecSnapshot` | [`models.py`](../../src/spec_orch/domain/models.py) | issue 路径上的冻结契约快照 |
| `TaskContract` | `domain/task_contract.py` | 结构化任务约束对象 |

判断原则：

- 这些对象本身承载 intent / acceptance / constraints / status
- 它们不是“某个流程顺手生成的文件”，而是业务意义明确的对象

关键边界：

- `Mission` 不是执行 attempt
- `Issue` 不是 session
- `SpecSnapshot` 不是简单日志文件

### 1.2 Execution Objects

这些对象回答“当前到底要跑什么”。

| 对象 | 当前代码锚点 | 说明 |
|---|---|---|
| `ExecutionPlan` | [`models.py`](../../src/spec_orch/domain/models.py) | mission 拆解后的执行计划 |
| `Wave` | [`models.py`](../../src/spec_orch/domain/models.py) | 可并行批次 |
| `WorkPacket` | [`models.py`](../../src/spec_orch/domain/models.py) | mission 派生的叶子执行单元 |
| `RunResult` | [`models.py`](../../src/spec_orch/domain/models.py) | issue run 的结果对象 |
| `BuilderResult` | [`models.py`](../../src/spec_orch/domain/models.py) | 单次 builder 执行结果 |
| `VerificationSummary` | [`models.py`](../../src/spec_orch/domain/models.py) | 验证结果对象 |
| `PacketResult` / `WaveResult` | [`models.py`](../../src/spec_orch/domain/models.py) | packet / wave 执行结果 |

关键边界：

- `ExecutionPlan` 是计划对象，不是 lifecycle owner
- `WorkPacket` 是 execution unit，不是完整 run
- `RunResult` 是 issue 路径结果，不是 mission round 结果

### 1.3 Supervision / Decision Objects

这些对象回答“谁拥有闭环、谁决定下一步”。

| 对象 | 当前代码锚点 | 说明 |
|---|---|---|
| `RoundSummary` | [`models.py`](../../src/spec_orch/domain/models.py) | 一轮 supervised round 的汇总对象 |
| `RoundDecision` | [`models.py`](../../src/spec_orch/domain/models.py) | round 结束后的结构化决策 |
| `SessionOps` | [`models.py`](../../src/spec_orch/domain/models.py) | round 决策后的 session 操作 |
| `ReviewSummary` | [`models.py`](../../src/spec_orch/domain/models.py) | review 结果对象 |
| `GateVerdict` | [`models.py`](../../src/spec_orch/domain/models.py) | gate 判定对象 |
| `MissionState` | [`lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py) | mission lifecycle 的状态对象 |

关键边界：

- `RoundDecision` 是 supervision object，不是 packet result
- `MissionState` 是 lifecycle state，不是 `Mission` 本体
- `GateVerdict` 是 evidence/decision object，不是 contract object

## 2. Runtime Owners：当前真正拥有流程的人

这些不是领域对象，但它们是真正的 runtime owners。

### 2.1 issue 路径 owner

| owner | 当前代码锚点 | 拥有的闭环 |
|---|---|---|
| `RunController` | [`run_controller.py`](../../src/spec_orch/services/run_controller.py) | 单 issue 从 spec 到 gate 的完整 run |

判断：

- `RunController` 不是领域对象
- 但它是今天 issue 路径最强的 runtime owner

### 2.2 Mission 路径 owners

| owner | 当前代码锚点 | 拥有的闭环 |
|---|---|---|
| `MissionLifecycleManager` | [`lifecycle_manager.py`](../../src/spec_orch/services/lifecycle_manager.py) | mission phase 级推进 |
| `MissionExecutionService` | [`mission_execution_service.py`](../../src/spec_orch/services/mission_execution_service.py) | mission execution 的统一调用入口 |
| `RoundOrchestrator` | [`round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py) | round 级 execute-review-decide 闭环 |

判断：

- 它们也不是领域对象
- 但它们是 mission 路径的真实流程 owner

### 2.3 执行 owner 与对象的关系

最容易混淆的一点是：

- `Mission` 不是 `MissionLifecycleManager`
- `Issue` 不是 `RunController`
- `WorkPacket` 不是 `WorkerHandle`

前者是对象，后者是 owner。

## 3. Persistence Carriers：这些东西很重要，但它们不是领域对象

这一类最容易被误判。

| 载体 | 当前位置 | 当前作用 |
|---|---|---|
| `report.json` | issue workspace | 旧 run summary/state carrier |
| `run_artifact/live.json` | issue workspace | 新 unified persisted payload |
| `run_artifact/manifest.json` | issue workspace | artifact index |
| `progress.json` | issue workspace | stage checkpoint |
| `spec_snapshot.json` | issue workspace | contract snapshot file |
| `round_summary.json` | mission rounds | round summary persistence |
| `round_decision.json` | mission rounds | round decision persistence |
| `lifecycle_state.json` | `.spec_orch_runs/` | mission lifecycle carrier |

这些文件很重要，但要区分两件事：

1. **文件内容可能承载某个对象**
2. **文件本身不是对象**

例如：

- `MissionState` 是对象
- `lifecycle_state.json` 是它的 carrier

- `RoundDecision` 是对象
- `round_decision.json` 是它的 carrier

- `RunResult` 或 run snapshot 是对象级语义
- `report.json` / `live.json` 只是落盘载体

## 4. Protocols / Adapters：这些是接口边界，不是业务主语

`domain/protocols.py` 里定义的很多东西非常重要，但它们更多是**接口边界**，不是业务主语。

| 协议 | 作用 | 不应误判成什么 |
|---|---|---|
| `BuilderAdapter` | 把 issue/prompt 送给具体 agent CLI | 不等于 Issue/Run |
| `ReviewAdapter` | 生成 review summary | 不等于 ReviewSummary 本体 |
| `PacketExecutor` | 执行 packet | 不等于 WorkPacket |
| `WorkerHandle` | mission worker 的执行接口 | 不等于 Worker Session 本体 |
| `SupervisorAdapter` | 产出 `RoundDecision` | 不等于 Round 本体 |
| `WorkerHandleFactory` | 创建/复用 worker handle | 不等于 session state |

关键边界：

- adapter 是“如何执行”
- object 是“正在处理什么”
- result object 是“执行后得到了什么”

## 5. Shells：这些是入口壳，不是对象层

### 5.1 CLI 是 shell

例如：

- [`run_commands.py`](../../src/spec_orch/cli/run_commands.py)
- [`mission_commands.py`](../../src/spec_orch/cli/mission_commands.py)

它们的角色是：

- 接受用户命令
- 组装参数
- 调 runtime owner

CLI 不应该被看作领域对象层。

### 5.2 Dashboard 也是 shell

例如：

- `dashboard/app.py`
- `dashboard/routes.py`
- `dashboard/launcher.py`

它们的角色是：

- 给 operator 提供入口
- 暴露状态与控制面
- 驱动 mission launcher 和 review surfaces

Dashboard 是 control shell，不是 contract / execution object。

## 6. 当前最容易混的几组东西

### 6.1 `Mission` vs `MissionState` vs `MissionLifecycleManager`

| 名称 | 本质 |
|---|---|
| `Mission` | 契约对象 |
| `MissionState` | lifecycle 状态对象 |
| `MissionLifecycleManager` | lifecycle owner |

### 6.2 `Issue` vs `RunResult` vs `RunController`

| 名称 | 本质 |
|---|---|
| `Issue` | 输入对象 |
| `RunResult` | issue run 的结果对象 |
| `RunController` | issue run 的 owner |

### 6.3 `WorkPacket` vs `PacketResult` vs `PacketExecutor`

| 名称 | 本质 |
|---|---|
| `WorkPacket` | mission 派生的 execution unit |
| `PacketResult` | packet 执行结果 |
| `PacketExecutor` | packet 执行接口 / owner 之一 |

### 6.4 `RoundSummary` vs `RoundDecision` vs `RoundOrchestrator`

| 名称 | 本质 |
|---|---|
| `RoundSummary` | round 的结果汇总对象 |
| `RoundDecision` | round 的下一步决策对象 |
| `RoundOrchestrator` | round 级闭环 owner |

### 6.5 `Session` vs `WorkerHandle` vs `session_id`

| 名称 | 本质 |
|---|---|
| `Session` | 当前 glossary 里的抽象 runtime identity |
| `WorkerHandle` | 对 session 发指令的执行接口 |
| `session_id` | session 的标识符 |

这三者今天也没有完全统一，但最少不能再混成一个东西。

## 7. 当前对象层的真实问题是什么

不是“完全没有对象”，而是三种问题叠加：

1. **对象有了，但 owner 没收口**
   - 同类语义挂在多个 owner 上

2. **对象有了，但 carrier 过强**
   - 大家容易把 `report.json`、`round_summary.json` 当成对象本身

3. **对象有了，但术语没对齐**
   - `Mission`
   - `MissionState`
   - `Round`
   - `Run`
   - `Session`
   - `Worker`
   - `Packet`

这些词目前跨层复用得太厉害

## 8. 这对下一步拆解意味着什么

这份文档不直接推出重构方案，但它至少给出三个清楚的边界。

### 8.1 先辨认对象，再决定抽象

下一步不是马上发明一个总抽象把所有东西收起来，而是先确认：

- 哪些对象本来就该保留分离
- 哪些 owner 只是实现分裂
- 哪些 carrier 只该留在 persistence 层

### 8.2 术语收口应优先围绕对象，而不是围绕 service

后续 glossary 扩展，更应该优先定义：

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOwner`
- `Supervisor`
- `Worker`
- `ArtifactCarrier`

而不是先围绕某个 service 文件名来命名。

### 8.3 当前最稳的判断

今天最稳的对象层判断是：

1. `Mission`、`Issue`、`ExecutionPlan`、`WorkPacket`、`RoundDecision` 都已经是对象
2. `RunController`、`MissionLifecycleManager`、`RoundOrchestrator` 是 owner，不是对象本体
3. `report.json`、`live.json`、`round_summary.json`、`lifecycle_state.json` 是 carrier，不是对象本体
4. CLI 和 dashboard 是 shell，不是对象层
5. adapter/protocol 是接口边界，不是业务主语

在这一步完成之前，不适合直接谈“最终统一抽象”；在这一步完成之后，才有资格继续讨论哪些对象其实可以收敛到同一语义族。
